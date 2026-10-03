"""七天进货计划表与单张手动签收接口的回归检查。"""

import os
from datetime import date, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.core.business_time import business_now
from app.core.database import async_engine, async_session_factory
from app.main import create_app
from app.models.department import Department
from app.models.enums import EmployeeRole, PurchaseStatus
from app.models.store import Store
from app.schemas.purchases_requests import CreatePurchaseRequest
from app.services import purchases as purchase_service
from app.services.purchase_planning import get_purchase_planning


def test_purchase_planning_and_manual_receive_routes_exist():
    paths = create_app().openapi()["paths"]
    assert "get" in paths["/api/v1/purchases/planning"]
    assert "put" in paths["/api/v1/purchases/{purchase_id}/receive"]


def test_purchase_creation_accepts_expected_arrival_date():
    requested = date.today() + timedelta(days=2)
    payload = CreatePurchaseRequest.model_validate(
        {
            "department_id": 1,
            "expected_arrival_date": requested.isoformat(),
            "items": [{"supplier_product_id": 1, "quantity": 2}],
        }
    )
    assert payload.expected_arrival_date == requested


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("now", "arrival", "locked"),
    [
        (datetime(2026, 10, 4, 11, 59, 59), date(2026, 10, 6), False),
        (datetime(2026, 10, 4, 12), date(2026, 10, 6), True),
        (datetime(2026, 10, 4, 13), date(2026, 10, 7), False),
        (datetime(2026, 10, 4, 9), date(2026, 10, 5), True),
        (datetime(2026, 10, 4, 12), None, True),
        (datetime(2026, 10, 4, 11), None, False),
    ],
)
async def test_order_cutoff_is_two_days_before_arrival(monkeypatch, now, arrival, locked):
    employee = SimpleNamespace(
        is_active=True, must_change_password=False, role=EmployeeRole.STORE_MANAGER
    )
    monkeypatch.setattr(purchase_service, "business_now", lambda: now)
    monkeypatch.setattr(purchase_service, "get_employee_by_id", AsyncMock(return_value=employee))
    department_lookup = AsyncMock(return_value=None)
    monkeypatch.setattr(purchase_service, "get_department_by_id", department_lookup)
    payload = CreatePurchaseRequest(
        department_id=1,
        expected_arrival_date=arrival,
        items=[{"supplier_product_id": 1, "quantity": 2}],
    )
    with pytest.raises(HTTPException) as error:
        await purchase_service.create_purchase_service(payload, 1, AsyncMock())
    if locked:
        assert error.value.status_code == 400
        assert "到货日前两天" in error.value.detail
        department_lookup.assert_not_awaited()
    else:
        # 有效时段进入下一项校验；不写入测试数据库。
        assert error.value.status_code == 404
        department_lookup.assert_awaited_once()


@pytest.mark.asyncio
async def test_manual_receive_targets_one_order_and_checks_department(monkeypatch):
    employee = SimpleNamespace(
        id=7,
        store_id=1,
        department_id=2,
        role=EmployeeRole.REGULAR_EMPLOYEE,
        is_active=True,
        must_change_password=False,
    )
    purchase = SimpleNamespace(
        id=9,
        store_id=1,
        department_id=2,
        status=PurchaseStatus.PENDING,
    )
    receive = AsyncMock(return_value=[purchase])
    detail = object()
    monkeypatch.setattr(purchase_service, "get_employee_by_id", AsyncMock(return_value=employee))
    monkeypatch.setattr(purchase_service, "get_purchase_by_id", AsyncMock(return_value=purchase))
    monkeypatch.setattr(purchase_service, "auto_receive_due_purchases", receive)
    monkeypatch.setattr(
        purchase_service, "get_purchase_detail_service", AsyncMock(return_value=detail)
    )
    db = AsyncMock()
    assert await purchase_service.receive_purchase_service(9, 7, db) is detail
    assert receive.await_args.kwargs["only_purchase_id"] == 9
    assert receive.await_args.kwargs["employee_id"] == 7
    db.commit.assert_awaited_once()

    purchase.department_id = 3
    receive.reset_mock()
    with pytest.raises(HTTPException) as error:
        await purchase_service.receive_purchase_service(9, 7, db)
    assert error.value.status_code == 403
    receive.assert_not_awaited()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_mysql_purchase_planning_uses_current_store():
    if os.getenv("RUN_MYSQL_TESTS") != "1":
        pytest.skip("set RUN_MYSQL_TESTS=1 to query the demonstration database")
    try:
        async with async_session_factory() as db:
            store = await db.scalar(select(Store).where(Store.is_active.is_(True)).limit(1))
            department = await db.scalar(
                select(Department).where(Department.is_active.is_(True)).limit(1)
            )
            if store is None or department is None:
                pytest.skip("active store and department are required")
            db.info["read_store_id"] = store.id
            result = await get_purchase_planning(
                department.id, business_now().date() + timedelta(days=2), db
            )
            assert len(result["days"]) == 7
            for item in result["items"]:
                assert len(item["days"]) == 7
                assert item["saleable_stock"] >= 0
    finally:
        await async_engine.dispose()
