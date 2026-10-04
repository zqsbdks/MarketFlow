from datetime import date, datetime

from sqlalchemy import select

from app.models.purchase_plan import PurchasePlan
from app.models.employee import Employee
from app.models.supplier_product import SupplierProduct
from app.schemas.purchase_plan import SaveMinimumStock, SavePurchasePlan
from app.services import purchase_plan_submission as service
from app.services.replenishment import refresh_automatic_plans, simulate_replenishment

NOW = datetime(2026, 10, 4, 21)
DAY = date(2026, 10, 6)


def simulate(stock=0, floor=0, demand=0, incoming=None, overrides=None, expiry=None):
    return simulate_replenishment(
        NOW,
        [DAY],
        {1: demand},
        [(NOW.date(), expiry, stock)],
        incoming or [],
        floor,
        7,
        overrides or {},
    )[DAY]


def test_floor_is_remaining_stock_not_minimum_order():
    assert simulate(stock=20, floor=10)["planned_quantity"] == 0
    assert simulate(stock=8, floor=10)["planned_quantity"] == 2
    assert simulate(stock=8, floor=10, demand=5)["planned_quantity"] == 7
    assert simulate(stock=0)["planned_quantity"] == 0


def test_expiring_stock_and_same_day_arrivals():
    assert simulate(stock=20, floor=10, expiry=date(2026, 10, 5))["planned_quantity"] == 10
    assert (
        simulate(stock=0, floor=10, incoming=[(DAY, date(2026, 10, 10), 12)])["planned_quantity"]
        == 0
    )
    assert (
        simulate(stock=0, floor=10, incoming=[(DAY, date(2026, 10, 5), 12)])["planned_quantity"]
        == 10
    )


def test_manual_zero_and_positive_take_priority():
    assert simulate(floor=10, overrides={DAY: 0})["planned_quantity"] == 0
    assert simulate(floor=10, overrides={DAY: 25})["planned_quantity"] == 25
    assert simulate(floor=10, overrides={DAY: 0})["is_manual"]


def test_next_day_counts_previous_plan_and_expiration():
    days = [DAY, date(2026, 10, 7)]
    result = simulate_replenishment(NOW, days, {1: 5, 2: 3}, [], [], 10, 7, {})
    assert result[DAY]["planned_quantity"] == 15
    assert result[days[1]]["planned_quantity"] == 3
    result = simulate_replenishment(NOW, days, {1: 5, 2: 3}, [], [], 10, 7, {DAY: 0})
    assert result[days[1]]["planned_quantity"] == 13


async def test_background_plans_floor_and_restore_manual_override(store_database, monkeypatch):
    now = datetime(2026, 10, 4, 11)
    monkeypatch.setattr(service, "business_now", lambda: now)
    async with store_database() as db:
        (await db.get(Employee, 5)).must_change_password = True
        await db.commit()
        db.info.update(write_store_id=1, read_store_id=1)
        await service.save_minimum_stock(
            SaveMinimumStock(department_id=1, supplier_product_id=1, minimum_stock=10), 1, db
        )
        assert (await db.get(SupplierProduct, 1)).minimum_stock == 10
    async with store_database() as db:
        assert await refresh_automatic_plans(db, now) == 14
    async with store_database() as db:
        db.info.update(write_store_id=1, read_store_id=1)
        plan = await db.scalar(
            select(PurchasePlan).where(PurchasePlan.store_id == 1, PurchasePlan.arrival_date == DAY)
        )
        assert plan.automatic_quantities == {"1": 10}
        assert plan.quantities == {}
        await service.save_purchase_plan(
            SavePurchasePlan(department_id=1, arrival_date=DAY, supplier_product_id=1, quantity=0),
            1,
            db,
        )
    async with store_database() as db:
        await refresh_automatic_plans(db, now)
        plan = await db.scalar(
            select(PurchasePlan).where(PurchasePlan.store_id == 1, PurchasePlan.arrival_date == DAY)
        )
        assert plan.quantities == {"1": 0}
        assert not await service.submit_due_plan(plan.id, db, datetime(2026, 10, 4, 12))
    async with store_database() as db:
        db.info.update(write_store_id=1, read_store_id=1)
        await service.save_purchase_plan(
            SavePurchasePlan(
                department_id=1, arrival_date=DAY, supplier_product_id=1, quantity=None
            ),
            1,
            db,
        )
    async with store_database() as db:
        plan = await db.scalar(
            select(PurchasePlan).where(PurchasePlan.store_id == 1, PurchasePlan.arrival_date == DAY)
        )
        assert plan.quantities == {}
        assert await service.submit_due_plan(plan.id, db, datetime(2026, 10, 4, 12))
