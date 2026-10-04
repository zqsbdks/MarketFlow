from datetime import date, datetime

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.models.operation_audit_log import OperationAuditLog
from app.models.purchase_item import PurchaseItem
from app.models.purchase_plan import PurchasePlan
from app.models.supplier_product import SupplierProduct
from app.schemas.purchase_plan import SaveMinimumStock, SavePurchasePlan
from app.services import purchase_plan_submission as service
from app.services.quantity_confirmation import quantity_reasons


def request(quantity=500, token=None):
    return SavePurchasePlan(
        department_id=1,
        supplier_product_id=1,
        arrival_date=date(2026, 10, 8),
        quantity=quantity,
        confirmation_token=token,
    )


def test_contextual_rules_do_not_flag_normal_high_volume():
    assert not quantity_reasons(500, 400, 300)
    assert "possible_repeated_key" in quantity_reasons(99, 100, 20)
    assert not quantity_reasons(0, 10, 50)
    assert "possible_extra_zero" in quantity_reasons(500, 100, 50)
    assert "possible_repeated_key" in quantity_reasons(99, 12, 9)
    assert "far_above_reference" in quantity_reasons(500, 20, 0)


@pytest.mark.parametrize("quantity", [11, 22, 33, 44, 55, 66, 77, 88, 99, 111, 2222])
def test_repeated_digits_require_confirmation_even_with_high_demand(quantity):
    assert "possible_repeated_key" in quantity_reasons(quantity, 10000, 0)


@pytest.mark.parametrize("quantity", [0, 1, 9, 12, 34, 100, 101])
def test_other_digits_do_not_trigger_repeated_key_warning(quantity):
    assert "possible_repeated_key" not in quantity_reasons(quantity, 10000, 0)


async def test_33_must_be_confirmed_before_it_replaces_saved_order(store_database, monkeypatch):
    monkeypatch.setattr(service, "business_now", lambda: datetime(2026, 10, 4, 10))
    async with store_database() as db:
        db.info.update(write_store_id=1, read_store_id=1)
        await service.save_purchase_plan(request(15), 1, db)
        check = await service.save_purchase_plan(request(33), 1, db)
        assert check["confirmation_required"]
        assert "possible_repeated_key" in check["reasons"]
        assert (await db.scalar(select(PurchasePlan))).quantities == {"1": 15}
        result = await service.save_purchase_plan(request(33, check["confirmation_token"]), 1, db)
        assert result["quantity"] == 33


async def test_stepper_bypasses_typing_warnings_but_keeps_large_quantity_check(
    store_database, monkeypatch
):
    monkeypatch.setattr(service, "business_now", lambda: datetime(2026, 10, 4, 10))
    async with store_database() as db:
        db.info.update(write_store_id=1, read_store_id=1)
        payload = request(22)
        payload.input_method = "stepper"
        assert (await service.save_purchase_plan(payload, 1, db))["quantity"] == 22
        payload.quantity = 500
        check = await service.save_purchase_plan(payload, 1, db)
        assert check["confirmation_required"]
        assert check["reasons"] == ["far_above_reference"]


async def test_unconfirmed_quantity_never_enters_noon_order(store_database, monkeypatch):
    monkeypatch.setattr(service, "business_now", lambda: datetime(2026, 10, 4, 10))
    async with store_database() as db:
        db.info.update(write_store_id=1, read_store_id=1)
        await service.save_purchase_plan(request(15), 1, db)
        check = await service.save_purchase_plan(request(), 1, db)
        assert check["confirmation_required"] and not check["saved"]
        plan = await db.scalar(select(PurchasePlan))
        assert plan.quantities == {"1": 15}
        await db.commit()
        assert await service.submit_due_plan(plan.id, db, datetime(2026, 10, 6, 12))
        await db.commit()
        assert await db.scalar(select(PurchaseItem.quantity)) == 15


async def test_confirmed_order_is_saved_and_audited(store_database, monkeypatch):
    monkeypatch.setattr(service, "business_now", lambda: datetime(2026, 10, 4, 10))
    async with store_database() as db:
        db.info.update(write_store_id=1, read_store_id=1)
        check = await service.save_purchase_plan(request(), 1, db)
        result = await service.save_purchase_plan(request(token=check["confirmation_token"]), 1, db)
        assert result["quantity"] == 500
        audit = await db.scalar(
            select(OperationAuditLog).where(OperationAuditLog.action == "save_plan")
        )
        assert audit.after_data["confirmation"]["confirmed"]
        assert audit.after_data["confirmation"]["reasons"]


async def test_confirmation_cannot_be_reused_for_different_quantity_or_employee(
    store_database, monkeypatch
):
    monkeypatch.setattr(service, "business_now", lambda: datetime(2026, 10, 4, 10))
    async with store_database() as db:
        db.info.update(write_store_id=1, read_store_id=1)
        check = await service.save_purchase_plan(request(), 1, db)
        token = check["confirmation_token"]
        assert (await service.save_purchase_plan(request(501, token), 1, db))[
            "confirmation_required"
        ]
        assert (await service.save_purchase_plan(request(500, token), 2, db))[
            "confirmation_required"
        ]
        assert (await service.save_purchase_plan(request(500, token + "x"), 1, db))[
            "confirmation_required"
        ]
        assert (await db.scalar(select(PurchasePlan))).quantities == {}


async def test_minimum_stock_confirmation_and_expiry(store_database, monkeypatch):
    monkeypatch.setattr(service, "business_now", lambda: datetime(2026, 10, 4, 10))
    clock = [1000]
    monkeypatch.setattr("app.services.quantity_confirmation.time.time", lambda: clock[0])
    async with store_database() as db:
        db.info.update(write_store_id=1, read_store_id=1)
        payload = SaveMinimumStock(department_id=1, supplier_product_id=1, minimum_stock=500)
        check = await service.save_minimum_stock(payload, 1, db)
        assert (await db.get(SupplierProduct, 1)).minimum_stock == 0
        payload.confirmation_token = check["confirmation_token"]
        clock[0] += 601
        check = await service.save_minimum_stock(payload, 1, db)
        assert check["confirmation_required"]
        payload.confirmation_token = check["confirmation_token"]
        assert (await service.save_minimum_stock(payload, 1, db))["minimum_stock"] == 500


async def test_confirmation_does_not_bypass_cutoff(store_database, monkeypatch):
    monkeypatch.setattr(service, "business_now", lambda: datetime(2026, 10, 4, 10))
    async with store_database() as db:
        db.info.update(write_store_id=1, read_store_id=1)
        check = await service.save_purchase_plan(request(), 1, db)
        monkeypatch.setattr(service, "business_now", lambda: datetime(2026, 10, 6, 12))
        with pytest.raises(HTTPException):
            await service.save_purchase_plan(request(token=check["confirmation_token"]), 1, db)
