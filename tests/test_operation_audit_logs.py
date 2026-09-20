"""库存变动流水业务组装和路由测试。"""

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

from sqlalchemy.ext.asyncio import AsyncSession

from app.main import create_app
from app.models.enums import EmployeeRole
from app.services.operation_audit_logs import get_inventory_movements_service


# region 库存变动流水业务测试
async def test_inventory_movement_service_builds_readable_quantity_change(monkeypatch) -> None:
    """进货创建批次时把变动前视为0，并计算正数入库量。"""

    employee = SimpleNamespace(
        id=1,
        role=EmployeeRole.STORE_MANAGER,
        is_active=True,
        must_change_password=False,
    )
    audit_log = SimpleNamespace(
        id=8,
        target_id=12,
        employee_id=None,
        action="create_batch",
        before_data=None,
        after_data={"remaining_quantity": 30},
        reason="进货单签收入库",
        created_at=datetime(2026, 9, 20, 12, 0),
    )

    async def get_employee(**_kwargs):
        return employee

    async def get_movements(**_kwargs):
        return [
            (
                audit_log,
                None,
                "BAT202609200001",
                3,
                "P00003",
                "测试商品",
            )
        ], 1

    monkeypatch.setattr("app.services.operation_audit_logs.get_employee_by_id", get_employee)
    monkeypatch.setattr(
        "app.services.operation_audit_logs.get_inventory_movements",
        get_movements,
    )

    result = await get_inventory_movements_service(
        page=1,
        page_size=20,
        keyword=None,
        action=None,
        batch_id=None,
        product_id=None,
        start_time=None,
        end_time=None,
        current_employee_id=employee.id,
        db=AsyncMock(spec=AsyncSession),
    )

    assert result.total == 1
    assert result.items[0].action_name == "进货入库"
    assert result.items[0].before_quantity == 0
    assert result.items[0].change_quantity == 30
    assert result.items[0].after_quantity == 30


# endregion


# region 库存变动流水路由测试
def test_inventory_movement_route_is_registered() -> None:
    """库存流水查询接口已注册到统一API前缀下。"""

    operation = create_app().openapi()["paths"]["/api/v1/operation-audit-logs/inventory-movements"]
    assert "get" in operation
    assert operation["get"]["summary"] == "获取库存变动流水"


# endregion
