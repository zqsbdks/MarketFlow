"""供应商商品目录业务测试。"""

from datetime import datetime
from decimal import Decimal
from unittest.mock import AsyncMock

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.employee import Employee
from app.models.enums import EmployeeRole
from app.models.supplier import Supplier
from app.models.supplier_product import SupplierProduct
from app.schemas.supplier_products_requests import (
    SupplierProductCreateRequest,
    SupplierProductUpdateRequest,
)
from app.services.supplier_products import (
    create_supplier_product_service,
    get_supplier_product_detail_service,
    get_supplier_products_list_service,
    update_supplier_product_service,
    update_supplier_product_status_service,
)


def build_employee(role: EmployeeRole = EmployeeRole.STORE_MANAGER) -> Employee:
    """构造可以正常使用系统的员工。"""

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
    """构造供应商测试对象。"""

    now = datetime(2026, 9, 11, 9, 0)
    return Supplier(
        id=1,
        supplier_no="SUP00001",
        name="测试供应商",
        is_active=is_active,
        created_at=now,
        updated_at=now,
    )


def build_supplier_product(is_active: bool = True) -> SupplierProduct:
    """构造已经加载供应商关系的目录商品。"""

    now = datetime(2026, 9, 11, 9, 0)
    supplier_product = SupplierProduct(
        id=1,
        supplier_id=1,
        name="猪五花肉",
        unit_cost=Decimal("25.80"),
        shelf_life_days=7,
        is_active=is_active,
        created_at=now,
        updated_at=now,
    )
    supplier_product.supplier = build_supplier()
    return supplier_product


async def test_employee_can_get_supplier_product_list(monkeypatch) -> None:
    """普通员工可以查看分页后的供应商商品列表。"""

    employee = build_employee(EmployeeRole.REGULAR_EMPLOYEE)
    supplier_product = build_supplier_product()
    monkeypatch.setattr(
        "app.services.supplier_products.get_employee_by_id",
        AsyncMock(return_value=employee),
    )
    monkeypatch.setattr(
        "app.services.supplier_products.get_all_supplier_products",
        AsyncMock(return_value=([supplier_product], 1)),
    )

    result = await get_supplier_products_list_service(
        page=1,
        page_size=10,
        supplier_id=None,
        keyword=None,
        is_active=None,
        current_employee_id=employee.id,
        db=AsyncMock(spec=AsyncSession),
    )

    assert result.total == 1
    assert result.items[0].supplier_name == "测试供应商"


async def test_employee_can_get_supplier_product_detail(monkeypatch) -> None:
    """普通员工可以查看指定供应商商品详情。"""

    employee = build_employee(EmployeeRole.REGULAR_EMPLOYEE)
    supplier_product = build_supplier_product()
    monkeypatch.setattr(
        "app.services.supplier_products.get_employee_by_id",
        AsyncMock(return_value=employee),
    )
    monkeypatch.setattr(
        "app.services.supplier_products.get_supplier_product_by_id",
        AsyncMock(return_value=supplier_product),
    )

    result = await get_supplier_product_detail_service(
        supplier_product_id=1,
        current_employee_id=employee.id,
        db=AsyncMock(spec=AsyncSession),
    )

    assert result.name == "猪五花肉"


async def test_manager_can_create_supplier_product(monkeypatch) -> None:
    """店长可以向启用供应商的目录中添加不重名的商品。"""

    manager = build_employee()
    supplier = build_supplier()
    supplier_product = build_supplier_product()
    db = AsyncMock(spec=AsyncSession)
    create_record = AsyncMock(return_value=supplier_product)
    monkeypatch.setattr(
        "app.services.supplier_products.get_employee_by_id",
        AsyncMock(return_value=manager),
    )
    monkeypatch.setattr(
        "app.services.supplier_products.get_supplier_by_id",
        AsyncMock(return_value=supplier),
    )
    monkeypatch.setattr(
        "app.services.supplier_products.get_supplier_product_by_name",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr("app.services.supplier_products.create_supplier_product", create_record)
    monkeypatch.setattr(
        "app.services.supplier_products.get_supplier_product_by_id",
        AsyncMock(return_value=supplier_product),
    )

    result = await create_supplier_product_service(
        request=SupplierProductCreateRequest(
            supplier_id=1,
            name="猪五花肉",
            unit_cost=Decimal("25.80"),
            shelf_life_days=7,
        ),
        current_employee_id=manager.id,
        db=db,
    )

    create_record.assert_awaited_once()
    db.commit.assert_awaited_once()
    assert result.supplier_id == supplier.id


async def test_manager_can_update_supplier_product_status(monkeypatch) -> None:
    """店长可以停用供应商商品。"""

    manager = build_employee()
    original = build_supplier_product(is_active=True)
    updated = build_supplier_product(is_active=False)
    get_product = AsyncMock(side_effect=[original, updated])
    update_status = AsyncMock()
    db = AsyncMock(spec=AsyncSession)
    monkeypatch.setattr(
        "app.services.supplier_products.get_employee_by_id",
        AsyncMock(return_value=manager),
    )
    monkeypatch.setattr("app.services.supplier_products.get_supplier_product_by_id", get_product)
    monkeypatch.setattr(
        "app.services.supplier_products.update_supplier_product_status",
        update_status,
    )

    result = await update_supplier_product_status_service(
        supplier_product_id=1,
        is_active=False,
        current_employee_id=manager.id,
        db=db,
    )

    update_status.assert_awaited_once()
    db.commit.assert_awaited_once()
    assert result.is_active is False


async def test_manager_can_update_supplier_product_details(monkeypatch) -> None:
    """店长可以只修改实际传入的供应商商品字段。"""

    manager = build_employee()
    original = build_supplier_product()
    updated = build_supplier_product()
    updated.unit_cost = Decimal("26.50")
    get_product = AsyncMock(side_effect=[original, updated])
    update_record = AsyncMock()
    db = AsyncMock(spec=AsyncSession)
    monkeypatch.setattr(
        "app.services.supplier_products.get_employee_by_id",
        AsyncMock(return_value=manager),
    )
    monkeypatch.setattr("app.services.supplier_products.get_supplier_product_by_id", get_product)
    monkeypatch.setattr("app.services.supplier_products.update_supplier_product", update_record)

    result = await update_supplier_product_service(
        supplier_product_id=1,
        request=SupplierProductUpdateRequest(unit_cost=Decimal("26.50")),
        current_employee_id=manager.id,
        db=db,
    )

    update_record.assert_awaited_once_with(
        supplier_product_id=1,
        update_data={"unit_cost": Decimal("26.50")},
        db=db,
    )
    db.commit.assert_awaited_once()
    assert result.unit_cost == Decimal("26.50")
