"""真实隔离数据库验证计划覆盖、截止、自动下单与停机补处理。"""

from datetime import date, datetime

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select

from app.crud.purchases import create_purchase
from app.models.purchase import Purchase
from app.models.purchase_item import PurchaseItem
from app.models.purchase_plan import PurchasePlan
from app.schemas.purchase_plan import SavePurchasePlan
from app.schemas.purchases_requests import CreatePurchaseRequest
from app.services import purchase_plan_submission as service
from app.services.purchase_planning import get_purchase_planning


def payload(quantity=15, catalog=1):
    return SavePurchasePlan(
        department_id=1,
        arrival_date=date(2026, 10, 8),
        supplier_product_id=catalog,
        quantity=quantity,
    )


def context(db, store=1):
    db.info.update(write_store_id=store, read_store_id=store)


async def test_previous_day_arrivals_are_summed_without_entering_plan(store_database, monkeypatch):
    monkeypatch.setattr(
        "app.services.purchase_planning.business_now", lambda: datetime(2026, 10, 4, 13)
    )
    async with store_database() as db:
        for store, actor, quantity in [(1, 1, 15), (1, 1, 10), (2, 5, 99)]:
            context(db, store)
            await create_purchase(
                CreatePurchaseRequest(
                    department_id=1,
                    expected_arrival_date=date(2026, 10, 5),
                    items=[{"supplier_product_id": store, "quantity": quantity}],
                ),
                actor,
                db,
                ordered_at_override=datetime(2026, 10, 3, 12),
            )
        await db.commit()
    async with store_database() as db:
        context(db)
        planning = await get_purchase_planning(1, None, db)
        assert planning["previous_arrival_date"] == date(2026, 10, 5)
        assert planning["days"][0] == date(2026, 10, 6)
        item = next(row for row in planning["items"] if row["supplier_product_id"] == 1)
        assert item["previous_expected_quantity"] == 25
        assert item["previous_received_quantity"] == 0
        assert len(item["days"]) == 7


async def test_saved_quantity_replaces_and_survives_reload(store_database, monkeypatch):
    monkeypatch.setattr(service, "business_now", lambda: datetime(2026, 10, 4, 10))
    monkeypatch.setattr("app.services.purchase_planning.business_now", service.business_now)
    async with store_database() as db:
        context(db)
        await service.save_purchase_plan(payload(15), 1, db)
        await service.save_purchase_plan(payload(25), 1, db)
        assert await db.scalar(select(func.count(Purchase.id))) == 0
    async with store_database() as db:
        context(db)
        plan = await db.scalar(select(PurchasePlan))
        assert plan.quantities == {"1": 25}
        planning = await get_purchase_planning(1, date(2026, 10, 8), db)
        assert planning["items"][0]["days"][0]["planned_quantity"] == 25


async def test_noon_generates_once_with_final_quantity(store_database, monkeypatch):
    monkeypatch.setattr(service, "business_now", lambda: datetime(2026, 10, 4, 10))
    async with store_database() as db:
        context(db)
        await service.save_purchase_plan(payload(15), 1, db)
        await service.save_purchase_plan(payload(25), 1, db)
        plan_id = await db.scalar(select(PurchasePlan.id))
    async with store_database() as db:
        assert not await service.submit_due_plan(plan_id, db, datetime(2026, 10, 6, 11, 59, 59))
        assert await service.submit_due_plan(plan_id, db, datetime(2026, 10, 6, 12))
        await db.commit()
    async with store_database() as db:
        assert not await service.submit_due_plan(plan_id, db, datetime(2026, 10, 6, 13))
        assert await db.scalar(select(func.count(Purchase.id))) == 1
        assert await db.scalar(select(PurchaseItem.quantity)) == 25
        order = await db.scalar(select(Purchase))
        assert order.ordered_at == datetime(2026, 10, 6, 12)
        assert order.expected_arrival_at == datetime(2026, 10, 8, 12)


async def test_late_restart_and_store_isolation(store_database, monkeypatch):
    monkeypatch.setattr(service, "business_now", lambda: datetime(2026, 10, 4, 10))
    async with store_database() as db:
        context(db, 2)
        await service.save_purchase_plan(payload(7, 2), 5, db)
        plan_id = await db.scalar(select(PurchasePlan.id))
    async with store_database() as db:
        assert await service.submit_due_plan(plan_id, db, datetime(2026, 10, 10, 13))
        await db.commit()
        order = await db.scalar(select(Purchase))
        item = await db.scalar(select(PurchaseItem))
        assert order.store_id == item.store_id == 2
        assert item.product_id == 2
        assert order.expected_arrival_at > order.ordered_at


async def test_zero_cancels_item_without_empty_purchase(store_database, monkeypatch):
    monkeypatch.setattr(service, "business_now", lambda: datetime(2026, 10, 4, 10))
    async with store_database() as db:
        context(db)
        await service.save_purchase_plan(payload(15), 1, db)
        await service.save_purchase_plan(payload(0), 1, db)
        plan_id = await db.scalar(select(PurchasePlan.id))
        assert not await service.submit_due_plan(plan_id, db, datetime(2026, 10, 6, 12))
        assert await db.scalar(select(func.count(Purchase.id))) == 0


@pytest.mark.parametrize("actor,store,catalog", [(3, 1, 1), (4, 1, 1), (1, 2, 2), (2, 1, 2)])
async def test_unauthorized_or_cross_store_catalog_rejected(
    store_database, monkeypatch, actor, store, catalog
):
    monkeypatch.setattr(service, "business_now", lambda: datetime(2026, 10, 4, 10))
    async with store_database() as db:
        context(db, store)
        with pytest.raises(HTTPException):
            await service.save_purchase_plan(payload(15, catalog), actor, db)


async def test_cutoff_rejects_edit_even_before_worker_runs(store_database, monkeypatch):
    monkeypatch.setattr(service, "business_now", lambda: datetime(2026, 10, 6, 12))
    async with store_database() as db:
        context(db)
        with pytest.raises(HTTPException) as error:
            await service.save_purchase_plan(payload(25), 1, db)
        assert error.value.status_code == 400
        assert await db.scalar(select(func.count(PurchasePlan.id))) == 0
