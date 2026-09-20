"""库存批次废弃业务和接口注册测试。"""

from datetime import date, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.main import create_app
from app.models.enums import EmployeeRole
from app.schemas.inventory_batches_requests import InventoryBatchDiscardRequest
from app.services.inventory_batches import discard_expired_inventory_batch_service


# region 废弃过期批次业务测试
async def test_manager_can_discard_expired_inventory_batch(monkeypatch) -> None:
    """店长可以废弃真正过期且仍有剩余库存的批次。"""

    employee = SimpleNamespace(
        id=1,
        role=EmployeeRole.STORE_MANAGER,
        department_id=None,
        is_active=True,
        must_change_password=False,
    )
    batch = SimpleNamespace(
        id=9,
        expiration_date=date.today() - timedelta(days=1),
        remaining_quantity=6,
        product=SimpleNamespace(department_id=2),
    )
    expected_response = object()
    discard_record = AsyncMock()

    async def get_employee(**_kwargs):
        return employee

    async def get_batch(**_kwargs):
        return batch

    async def get_detail(**_kwargs):
        return expected_response

    monkeypatch.setattr("app.services.inventory_batches.get_employee_by_id", get_employee)
    monkeypatch.setattr("app.services.inventory_batches.get_inventory_batch_by_id", get_batch)
    monkeypatch.setattr(
        "app.services.inventory_batches.discard_expired_inventory_batch",
        discard_record,
    )
    monkeypatch.setattr(
        "app.services.inventory_batches.get_inventory_batch_detail_service",
        get_detail,
    )
    db = AsyncMock(spec=AsyncSession)

    result = await discard_expired_inventory_batch_service(
        batch_id=batch.id,
        request=InventoryBatchDiscardRequest(reason="过期下架"),
        current_employee_id=employee.id,
        db=db,
    )

    assert result is expected_response
    discard_record.assert_awaited_once()
    db.commit.assert_awaited_once()


async def test_unexpired_inventory_batch_cannot_be_discarded(monkeypatch) -> None:
    """尚未过期的批次不能通过过期废弃接口扣减库存。"""

    employee = SimpleNamespace(
        id=1,
        role=EmployeeRole.STORE_MANAGER,
        department_id=None,
        is_active=True,
        must_change_password=False,
    )
    batch = SimpleNamespace(
        id=10,
        expiration_date=date.today(),
        remaining_quantity=6,
        product=SimpleNamespace(department_id=2),
    )

    async def get_employee(**_kwargs):
        return employee

    async def get_batch(**_kwargs):
        return batch

    monkeypatch.setattr("app.services.inventory_batches.get_employee_by_id", get_employee)
    monkeypatch.setattr("app.services.inventory_batches.get_inventory_batch_by_id", get_batch)

    with pytest.raises(HTTPException) as exc_info:
        await discard_expired_inventory_batch_service(
            batch_id=batch.id,
            request=InventoryBatchDiscardRequest(),
            current_employee_id=employee.id,
            db=AsyncMock(spec=AsyncSession),
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "只有已经过期的库存批次可以废弃"


# endregion


# region 废弃过期批次路由测试
def test_discard_expired_inventory_batch_route_is_registered() -> None:
    """废弃接口已经以 POST 方法注册到库存批次路由。"""

    operation = create_app().openapi()["paths"]["/api/v1/inventory-batches/{batch_id}/discard"]
    assert "post" in operation
    assert operation["post"]["summary"] == "废弃过期批次库存"


# endregion
