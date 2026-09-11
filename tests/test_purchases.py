"""进货单列表业务测试。"""

from datetime import datetime
from decimal import Decimal
from unittest.mock import AsyncMock

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.department import Department
from app.models.employee import Employee
from app.models.enums import EmployeeRole, PurchaseStatus
from app.models.purchase import Purchase
from app.services.purchases import get_purchases_list_service


def build_employee() -> Employee:
    """构造可以正常查看进货单的员工。"""

    return Employee(
        id=1,
        employee_no="E00001",
        name="测试员工",
        password_hash="test-hash",
        role=EmployeeRole.REGULAR_EMPLOYEE,
        department_id=1,
        is_active=True,
        must_change_password=False,
    )


def build_purchase() -> Purchase:
    """构造已经加载部门和员工关系的进货单。"""

    ordered_at = datetime(2026, 9, 11, 9, 0)
    purchase = Purchase(
        id=1,
        purchase_no="PUR202609110001",
        department_id=1,
        created_by=1,
        received_by=None,
        ordered_at=ordered_at,
        expected_arrival_at=datetime(2026, 9, 13, 9, 0),
        arrived_at=None,
        total_amount=Decimal("2580.00"),
        status=PurchaseStatus.PENDING,
        created_at=ordered_at,
        updated_at=ordered_at,
    )
    purchase.department = Department(id=1, name="精肉部", is_active=True)
    purchase.created_by_employee = build_employee()
    purchase.received_by_employee = None
    return purchase


async def test_employee_can_get_purchase_list_with_item_totals(monkeypatch) -> None:
    """列表响应会包含明细行数和全部商品数量。"""

    employee = build_employee()
    purchase = build_purchase()
    query_purchases = AsyncMock(return_value=([(purchase, 2, 30)], 1))
    monkeypatch.setattr(
        "app.services.purchases.get_employee_by_id",
        AsyncMock(return_value=employee),
    )
    monkeypatch.setattr("app.services.purchases.get_all_purchases", query_purchases)

    result = await get_purchases_list_service(
        page=1,
        page_size=10,
        purchase_no=None,
        department_id=None,
        ordered_at=None,
        arrived_at=None,
        purchase_status=None,
        current_employee_id=employee.id,
        db=AsyncMock(spec=AsyncSession),
    )

    assert result.total == 1
    assert result.items[0].item_count == 2
    assert result.items[0].total_quantity == 30
    assert result.items[0].received_by_name is None
