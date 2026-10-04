"""Procurement-to-sale and notice lifecycles using real business services and ORM."""

from datetime import datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select
from test_store_policy import request

from app.core.store_policy import configure_store_context
from app.models.employee import Employee
from app.models.inventory_batch import InventoryBatch
from app.models.operation_audit_log import OperationAuditLog
from app.models.product import Product
from app.models.purchase import Purchase
from app.models.sale import Sale
from app.schemas.contact_notices_requests import (
    ContactNoticeActionRequest,
    ContactNoticeWriteRequest,
)
from app.schemas.discount_rule_requests import (
    AddDiscountRuleProductsRequest,
    CreateDiscountRuleRequest,
)
from app.schemas.purchases_requests import CreatePurchaseRequest
from app.schemas.sales_requests import CreateSaleRequest
from app.services import discount_rule, purchases, sales
from app.services.contact_notices import action_notice, detail_notice, save_notice
from app.services.reports import overview_service


async def test_order_receive_discount_sale_inventory_audit_and_reports(store_database, monkeypatch):
    clock = [datetime(2026, 10, 4, 10)]
    for module in (purchases, sales, discount_rule):
        monkeypatch.setattr(module, "business_now", lambda: clock[0])
    monkeypatch.setattr("app.crud.sales.business_now", lambda: clock[0])
    async with store_database() as db:
        await configure_store_context(
            request("/api/v1/purchases", "POST"), await db.get(Employee, 1), db
        )
        purchase_request = CreatePurchaseRequest(
            department_id=1,
            client_request_id=uuid4(),
            expected_arrival_date=clock[0].date() + timedelta(days=2),
            items=[{"supplier_product_id": 1, "quantity": 10}],
        )
        order = await purchases.create_purchase_service(purchase_request, 1, db)
        repeated = await purchases.create_purchase_service(purchase_request, 1, db)
        assert repeated.id == order.id
        assert await db.scalar(select(func.count(Purchase.id))) == 1
        clock[0] = datetime(2026, 10, 6, 12)
        await purchases.receive_purchase_service(order.id, 1, db)
        assert (await db.get(Product, 1)).stock_quantity == 10
        assert await db.scalar(select(func.count(InventoryBatch.id))) == 1
        with pytest.raises(HTTPException) as error:
            await purchases.receive_purchase_service(order.id, 1, db)
        assert error.value.status_code == 409
        rule = await discount_rule.create_discount_rule_service(
            CreateDiscountRuleRequest(
                department_id=1,
                name="20% off",
                discount_type="percentage",
                discount_value=Decimal("0.8"),
                schedule_type="once",
                starts_at=clock[0] - timedelta(hours=1),
                ends_at=clock[0] + timedelta(hours=1),
            ),
            1,
            db,
        )
        await discount_rule.add_discount_rule_products_service(
            rule.id, AddDiscountRuleProductsRequest(product_ids=[1]), 1, db
        )
        sale_request = CreateSaleRequest(
            client_request_id=uuid4(), items=[{"product_id": 1, "quantity": 3}]
        )
        preview = await sales.preview_sale_price_service(sale_request, 1, db)
        receipt = await sales.create_sale_service(sale_request, 1, db)
        assert receipt.total_amount == preview.total_amount == Decimal("24")
        assert receipt.discount_amount == Decimal("6")
        assert (await db.get(Product, 1)).stock_quantity == 7
        assert (await db.scalar(select(InventoryBatch))).remaining_quantity == 7
        assert (await sales.create_sale_service(sale_request, 1, db)).sale_no == receipt.sale_no
        assert await db.scalar(select(func.count(Sale.id))) == 1
        report = await overview_service(
            db, 1, clock[0] - timedelta(hours=1), clock[0] + timedelta(hours=1), None
        )
        assert report.revenue == Decimal("24")
        assert report.sales_cost == Decimal("15")
        assert report.gross_profit == Decimal("9")
        assert report.sales_quantity == 3
        assert await db.scalar(select(func.count(OperationAuditLog.id))) > 0
    async with store_database() as db:
        assert (await db.get(Product, 2)).stock_quantity == 0


async def test_store_notice_publishing_reading_confirming_and_closing(store_database):
    async with store_database() as db:
        await configure_store_context(
            request("/api/v1/contact-notices", "POST"), await db.get(Employee, 1), db
        )
        draft = await save_notice(
            ContactNoticeWriteRequest(
                title="Store announcement",
                content="Confirm please",
                target_type="personal",
                employee_ids=[2],
            ),
            1,
            db,
        )
        published = await action_notice(
            draft.id, "publish", ContactNoticeActionRequest(expected_version=draft.version), 1, db
        )
        assert published.recipient_count == 1
        await configure_store_context(
            request("/api/v1/contact-notices/1"), await db.get(Employee, 2), db
        )
        detail = await detail_notice(draft.id, 2, db)
        assert detail.read_at is not None
        confirmed = await action_notice(draft.id, "confirm", None, 2, db)
        assert confirmed.status == "closed"
        assert confirmed.close_reason == "all_confirmed"
        repeated = await action_notice(draft.id, "confirm", None, 2, db)
        assert repeated.confirmed_at == confirmed.confirmed_at
