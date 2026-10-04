"""真实事务验证废弃库存、批次分配、日期边界、幂等与门店权限。"""

from datetime import date, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import func, select
from test_store_policy import request

from app.core.store_policy import configure_store_context
from app.models.employee import Employee
from app.models.enums import InventoryBatchStatus, PurchaseStatus
from app.models.inventory_batch import InventoryBatch
from app.models.inventory_discard import InventoryDiscard
from app.models.operation_audit_log import OperationAuditLog
from app.models.product import Product
from app.models.purchase import Purchase
from app.models.purchase_item import PurchaseItem
from app.models.store import StoreDepartment
from app.schemas.inventory_discards import (
    DiscardCreateRequest,
    DiscardListRequest,
    DiscardPlanRequest,
)
from app.services import inventory_discards as service

NOW = datetime(2026, 10, 4, 10)


@pytest.fixture
async def discard_database(store_database, monkeypatch):
    monkeypatch.setattr(service, "business_now", lambda: NOW)
    async with store_database() as db:
        # 四个本店批次：已过期、今天到期、较晚到期、无到期日期。
        for store_id, expirations in [
            (1, [date(2026, 10, 3), NOW.date(), date(2026, 10, 8), None]),
            (2, [NOW.date()]),
        ]:
            for index, expiration in enumerate(expirations, 1):
                purchase = Purchase(
                    store_id=store_id,
                    purchase_no=f"PO-{store_id}-{index}",
                    department_id=1,
                    created_by=1 if store_id == 1 else 5,
                    received_by=2 if store_id == 1 else 5,
                    ordered_at=NOW - timedelta(days=5),
                    expected_arrival_at=NOW - timedelta(days=3),
                    arrived_at=NOW - timedelta(days=3),
                    status=PurchaseStatus.ARRIVED,
                    total_amount=Decimal(index) * 10,
                )
                db.add(purchase)
                await db.flush()
                item = PurchaseItem(
                    store_id=store_id,
                    purchase_id=purchase.id,
                    product_id=store_id,
                    supplier_product_id=store_id,
                    supplier_id=store_id,
                    product_name_snapshot=f"Product {store_id}",
                    supplier_name_snapshot="Supplier",
                    quantity=10,
                    unit_cost=Decimal(index),
                    subtotal=Decimal(index) * 10,
                    expiration_date=expiration,
                )
                db.add(item)
                await db.flush()
                db.add(
                    InventoryBatch(
                        store_id=store_id,
                        batch_no=f"LOT-{store_id}-{index}",
                        product_id=store_id,
                        purchase_item_id=item.id,
                        expiration_date=expiration,
                        initial_quantity=10,
                        remaining_quantity=10,
                        status=InventoryBatchStatus.AVAILABLE,
                        arrived_at=NOW - timedelta(days=3),
                    )
                )
            (await db.get(Product, store_id)).stock_quantity = len(expirations) * 10
        await db.commit()
    return store_database


def payload(**overrides):
    return DiscardCreateRequest(
        **{
            "product_id": 1,
            "quantity": 12,
            "reason_code": "damaged",
            "request_id": uuid4(),
            **overrides,
        }
    )


async def context(db, employee_id=1, store="1", method="POST", path="/api/v1/inventory-discards"):
    await configure_store_context(
        request(path, method, store), await db.get(Employee, employee_id), db
    )


async def test_fefo_preview_and_atomic_stock_cost_audit(discard_database):
    async with discard_database() as db:
        await context(db)
        stock = await service.get_discard_stock(1, 1, db)
        assert stock.available_quantity == 30  # 已过期的 10 件不参与手动分配。
        preview = await service.preview_discard(
            DiscardPlanRequest(product_id=1, quantity=12), 1, db
        )
        assert [(item.batch_no, item.quantity) for item in preview.items] == [
            ("LOT-1-2", 10),
            ("LOT-1-3", 2),
        ]
        assert preview.total_cost == Decimal("26.00")
        assert (await db.get(Product, 1)).stock_quantity == 40  # 预览不扣库存。
        result = await service.create_discard(payload(), 1, db)
        assert result.total_cost == preview.total_cost
        assert (await db.get(Product, 1)).stock_quantity == 28
        assert sum((await db.scalars(select(InventoryBatch.remaining_quantity))).all()) == 28
        logs = (
            await db.scalars(
                select(OperationAuditLog).where(OperationAuditLog.action == "discard_manual")
            )
        ).all()
        assert len(logs) == 2
        assert {log.after_data["discard_id"] for log in logs} == {result.id}
        assert {log.store_id for log in logs} == {1}


async def test_repeat_request_returns_original_record_without_deduction(discard_database):
    req = payload()
    async with discard_database() as db:
        await context(db)
        first = await service.create_discard(req, 1, db)
    async with discard_database() as db:
        await context(db)
        repeat = await service.create_discard(req, 1, db)
        assert first.id == repeat.id
        assert (await db.get(Product, 1)).stock_quantity == 28
        assert await db.scalar(select(func.count(InventoryDiscard.id))) == 1
        with pytest.raises(HTTPException) as error:
            await service.create_discard(payload(request_id=req.request_id, quantity=1), 1, db)
        assert error.value.status_code == 409


async def test_explicit_batch_does_not_deduct_earlier_batches(discard_database):
    async with discard_database() as db:
        await context(db)
        batch = await db.scalar(select(InventoryBatch).where(InventoryBatch.batch_no == "LOT-1-3"))
        result = await service.create_discard(payload(quantity=4, batch_id=batch.id), 1, db)
        assert result.items[0].batch_no == "LOT-1-3"
        assert result.total_cost == Decimal("12")
        early = await db.scalar(select(InventoryBatch).where(InventoryBatch.batch_no == "LOT-1-2"))
        assert early.remaining_quantity == 10


@pytest.mark.parametrize("quantity", [31, 100])
async def test_insufficient_stock_does_not_partially_deduct(discard_database, quantity):
    async with discard_database() as db:
        await context(db)
        with pytest.raises(HTTPException) as error:
            await service.create_discard(payload(quantity=quantity), 1, db)
        assert error.value.status_code == 400
        await db.rollback()
    async with discard_database() as db:
        assert (await db.get(Product, 1)).stock_quantity == 40
        assert await db.scalar(select(func.count(InventoryDiscard.id))) == 0


async def test_submission_revalidates_stock_after_preview(discard_database):
    async with discard_database() as db:
        await context(db)
        await service.preview_discard(DiscardPlanRequest(product_id=1, quantity=25), 1, db)
        await service.create_discard(payload(quantity=10), 1, db)
        with pytest.raises(HTTPException):
            await service.create_discard(payload(quantity=25), 1, db)
        assert (await db.get(Product, 1)).stock_quantity == 30


async def test_expired_auto_disposal_boundary_and_repeat(discard_database):
    async with discard_database() as db:
        assert await service.discard_expired_product(1, NOW.date(), db) == 1
        await db.commit()
        assert (await db.get(Product, 1)).stock_quantity == 30
        record = await db.scalar(select(InventoryDiscard))
        assert record.quantity == 10 and record.total_cost == Decimal("10")
        assert record.reason_code == "expired" and record.employee_id is None
        today_batch = await db.scalar(
            select(InventoryBatch).where(InventoryBatch.batch_no == "LOT-1-2")
        )
        assert today_batch.remaining_quantity == 10
        assert await service.discard_expired_product(1, NOW.date(), db) == 0
        await db.commit()
        assert await db.scalar(select(func.count(InventoryDiscard.id))) == 1
        assert await service.discard_expired_product(1, NOW.date() + timedelta(days=1), db) == 1
        await db.commit()
        assert (await db.get(Product, 1)).stock_quantity == 20


@pytest.mark.parametrize("employee_id", [3, 4])
async def test_contract_and_headquarters_cannot_manually_dispose(discard_database, employee_id):
    async with discard_database() as db:
        with pytest.raises(HTTPException) as error:
            await service.create_discard(payload(), employee_id, db)
        assert error.value.status_code == 403


async def test_cross_store_and_department_and_disabled_rejected(discard_database):
    async with discard_database() as db:
        with pytest.raises(HTTPException) as error:
            await service.create_discard(payload(product_id=2), 1, db)
        assert error.value.status_code == 403
        regular = await db.get(Employee, 2)
        regular.department_id = 2
        await db.commit()
        with pytest.raises(HTTPException) as error:
            await service.create_discard(payload(), 2, db)
        assert error.value.status_code == 403
        regular.department_id = 1
        link = await db.scalar(
            select(StoreDepartment).where(
                StoreDepartment.store_id == 1, StoreDepartment.department_id == 1
            )
        )
        link.is_active = False
        await db.commit()
        with pytest.raises(HTTPException) as error:
            await service.create_discard(payload(), 1, db)
        assert error.value.status_code == 400


async def test_filter_summary_pagination_and_headquarters_all_stores(discard_database):
    async with discard_database() as db:
        await service.create_discard(payload(quantity=1), 1, db)
        await service.create_discard(payload(quantity=2, reason_code="spoiled"), 2, db)
        await service.create_discard(payload(product_id=2, quantity=3), 5, db)
        await context(db, 4, "all", "GET", "/api/v1/inventory-discards/list")
        result = await service.list_discards(DiscardListRequest(page_size=1), 4, db)
        assert result.total == 3 and result.total_pages == 3
        assert result.total_quantity == 6 and result.total_cost == Decimal("9")
        filtered = await service.list_discards(
            DiscardListRequest(reason_code="spoiled", start_date=NOW.date(), end_date=NOW.date()),
            4,
            db,
        )
        assert filtered.total == 1 and filtered.total_quantity == 2
        assert filtered.total_cost == Decimal("4")
        await context(db, 4, "1", "GET", "/api/v1/inventory-discards/list")
        selected = await service.list_discards(DiscardListRequest(), 4, db)
        assert selected.total == 2 and selected.total_quantity == 3


async def test_invalid_selected_batch_and_zero_quantity(discard_database):
    async with discard_database() as db:
        await context(db)
        expired = await db.scalar(
            select(InventoryBatch.id).where(InventoryBatch.batch_no == "LOT-1-1")
        )
        with pytest.raises(HTTPException):
            await service.create_discard(payload(batch_id=expired), 1, db)
        assert (await db.get(Product, 1)).stock_quantity == 40
    for quantity in (0, -1, 1.5, True):
        with pytest.raises(ValidationError):
            payload(quantity=quantity)
    with pytest.raises(ValidationError):
        payload(reason_code="other")
    with pytest.raises(ValidationError):
        payload(reason_code="expired")
