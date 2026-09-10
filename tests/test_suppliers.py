"""供应商详情和状态修改业务测试。"""

from datetime import datetime
from unittest.mock import AsyncMock

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.employee import Employee
from app.models.enums import EmployeeRole
from app.models.supplier import Supplier
from app.services.suppliers import get_supplier_detail_service, update_supplier_status_service


def build_employee(role: EmployeeRole = EmployeeRole.STORE_MANAGER) -> Employee:
    """构造已启用且已经修改初始密码的员工。"""

    return Employee(
        id=1,
        employee_no="E00001",
        name="测试员工",
        password_hash="test-hash",
        role=role,
        department_id=None,
        is_active=True,
        must_change_password=False,
    )


def build_supplier(is_active: bool = True) -> Supplier:
    """构造带有响应所需字段的供应商。"""

    created_at = datetime(2026, 9, 10, 9, 0)
    return Supplier(
        id=1,
        supplier_no="SUP00001",
        name="测试供应商",
        contact_name=None,
        phone=None,
        address=None,
        is_active=is_active,
        created_at=created_at,
        updated_at=created_at,
    )


async def test_logged_in_employee_can_get_supplier_detail(monkeypatch) -> None:
    """普通已登录员工也可以查看供应商详情。"""

    employee = build_employee(EmployeeRole.REGULAR_EMPLOYEE)
    supplier = build_supplier()

    async def get_employee(**_kwargs):
        return employee

    async def get_supplier(**_kwargs):
        return supplier

    monkeypatch.setattr("app.services.suppliers.get_employee_by_id", get_employee)
    monkeypatch.setattr("app.services.suppliers.get_supplier_by_id", get_supplier)

    result = await get_supplier_detail_service(
        supplier_id=supplier.id,
        current_employee_id=employee.id,
        db=AsyncMock(spec=AsyncSession),
    )

    assert result.id == supplier.id
    assert result.name == supplier.name


async def test_manager_can_update_supplier_status(monkeypatch) -> None:
    """店长修改状态后会提交事务并返回更新后的供应商。"""

    manager = build_employee()
    original_supplier = build_supplier(is_active=True)
    updated_supplier = build_supplier(is_active=False)
    supplier_results = iter([original_supplier, updated_supplier])

    async def get_employee(**_kwargs):
        return manager

    async def get_supplier(**_kwargs):
        return next(supplier_results)

    update_status = AsyncMock()
    db = AsyncMock(spec=AsyncSession)
    monkeypatch.setattr("app.services.suppliers.get_employee_by_id", get_employee)
    monkeypatch.setattr("app.services.suppliers.get_supplier_by_id", get_supplier)
    monkeypatch.setattr("app.services.suppliers.put_supplier_status", update_status)

    result = await update_supplier_status_service(
        supplier_id=original_supplier.id,
        is_active=False,
        current_employee_id=manager.id,
        db=db,
    )

    update_status.assert_awaited_once_with(
        supplier_id=original_supplier.id,
        is_active=False,
        db=db,
    )
    db.commit.assert_awaited_once()
    assert result.is_active is False
