"""商品列表请求、Service 与 API 响应测试。"""

from decimal import Decimal
from unittest.mock import AsyncMock

from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies.auth import get_current_employee_id
from app.dependencies.db import get_db
from app.main import create_app
from app.models.category import Category
from app.models.department import Department
from app.models.employee import Employee
from app.models.enums import EmployeeRole, ProductStatus
from app.models.product import Product
from app.schemas.products_responses import ProductsListResponse
from app.services.products import get_products_list_service


def build_manager() -> Employee:
    """构造已修改初始密码且处于启用状态的店长。"""

    return Employee(
        id=1,
        employee_no="E00001",
        name="测试店长",
        password_hash="test-password-hash",
        role=EmployeeRole.STORE_MANAGER,
        department_id=None,
        is_active=True,
        must_change_password=False,
    )


def build_product() -> Product:
    """构造带部门和分类关系的商品测试对象。"""

    department = Department(id=1, code="MEAT", name="精肉部", is_active=True)
    category = Category(id=1, department_id=1, name="牛肉", is_active=True)
    return Product(
        id=1,
        product_no="P00001",
        name="国产牛肉",
        department_id=1,
        category_id=1,
        department=department,
        category=category,
        purchase_price=Decimal("50.00"),
        sale_price=Decimal("68.00"),
        stock_quantity=10,
        status=ProductStatus.ON_SALE,
    )


async def override_db():
    """路由测试使用的占位数据库依赖。"""

    yield None


async def override_manager_id() -> int:
    """路由测试固定使用店长 ID。"""

    return 1


# region Service 测试
async def test_products_list_service_returns_department_and_category(monkeypatch) -> None:
    """商品列表同时返回不可为空的部门名称和分类名称。"""

    manager = build_manager()
    product = build_product()

    async def get_current(**_kwargs):
        return manager

    async def get_products(**_kwargs):
        return [product], 1

    monkeypatch.setattr("app.services.products.get_employee_by_id", get_current)
    monkeypatch.setattr("app.services.products.get_products_list", get_products)

    result = await get_products_list_service(
        page=1,
        page_size=10,
        keyword=None,
        department_id=None,
        category_id=None,
        status=None,
        current_employee_id=manager.id,
        db=AsyncMock(spec=AsyncSession),
    )

    assert result.total == 1
    assert result.total_pages == 1
    assert result.items[0].department_name == "精肉部"
    assert result.items[0].category_name == "牛肉"


# endregion


# region 路由测试
def test_products_list_route_returns_documented_response(monkeypatch) -> None:
    """商品列表路由已挂载，并使用项目统一响应格式。"""

    async def get_products(**_kwargs):
        return ProductsListResponse(
            items=[],
            page=1,
            page_size=10,
            total=0,
            total_pages=0,
        )

    monkeypatch.setattr("app.routers.products.get_products_list_service", get_products)
    application = create_app()
    application.dependency_overrides[get_db] = override_db
    application.dependency_overrides[get_current_employee_id] = override_manager_id

    with TestClient(application) as client:
        response = client.get("/api/v1/products/list")

    assert response.status_code == 200
    assert response.json() == {
        "code": 200,
        "message": "商品列表获取成功",
        "data": {
            "items": [],
            "page": 1,
            "page_size": 10,
            "total": 0,
            "total_pages": 0,
        },
    }


# endregion
