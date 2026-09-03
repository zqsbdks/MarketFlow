"""销售单列表 Service 与 API 响应测试。"""

from datetime import datetime
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies.auth import get_current_employee_id
from app.dependencies.db import get_db
from app.main import create_app
from app.models.employee import Employee
from app.models.enums import EmployeeRole, ProductStatus, SaleSource
from app.models.product import Product
from app.models.sale import Sale
from app.models.sale_item import SaleItem
from app.schemas.sales_responses import SalesListResponse
from app.services.sales import get_sales_list_service


def build_employee() -> Employee:
    """构造可以查看销售数据的已启用员工。"""

    return Employee(
        id=2,
        employee_no="E00002",
        name="测试员工",
        password_hash="test-password-hash",
        role=EmployeeRole.REGULAR_EMPLOYEE,
        department_id=1,
        is_active=True,
        must_change_password=False,
    )


def build_sale() -> Sale:
    """构造包含两种商品、三件商品的销售单。"""

    product = Product(
        id=1,
        product_no="P00001",
        name="测试商品",
        department_id=1,
        category_id=1,
        purchase_price=Decimal("10.00"),
        sale_price=Decimal("15.00"),
        stock_quantity=10,
        status=ProductStatus.ON_SALE,
    )
    sale = Sale(
        id=1,
        sale_no="S202609010001",
        sold_at=datetime(2026, 9, 1, 10, 20),
        total_amount=Decimal("45.00"),
        total_cost=Decimal("30.00"),
        gross_profit=Decimal("15.00"),
        source=SaleSource.DEMO_SEED,
    )
    sale.items = [
        SaleItem(
            id=1,
            sale_id=1,
            product_id=1,
            product=product,
            product_no_snapshot="P00001",
            product_name_snapshot="商品一",
            department_id=1,
            quantity=2,
            unit_price=Decimal("15.00"),
            unit_cost=Decimal("10.00"),
            subtotal=Decimal("30.00"),
            cost_subtotal=Decimal("20.00"),
        ),
        SaleItem(
            id=2,
            sale_id=1,
            product_id=1,
            product=product,
            product_no_snapshot="P00001",
            product_name_snapshot="商品二",
            department_id=1,
            quantity=1,
            unit_price=Decimal("15.00"),
            unit_cost=Decimal("10.00"),
            subtotal=Decimal("15.00"),
            cost_subtotal=Decimal("10.00"),
        ),
    ]
    return sale


async def override_db():
    """路由测试使用的占位数据库依赖。"""

    yield None


async def override_employee_id() -> int:
    """路由测试固定使用员工 ID。"""

    return 2


# region Service 测试
async def test_sales_list_service_builds_receipt_summary(monkeypatch) -> None:
    """一张销售单正确计算商品总数量和明细种类数。"""

    async def get_employee(**_kwargs):
        return build_employee()

    async def get_sales(**_kwargs):
        return [build_sale()], 1

    monkeypatch.setattr("app.services.sales.get_employee_by_id", get_employee)
    monkeypatch.setattr("app.services.sales.get_sales_list", get_sales)

    result = await get_sales_list_service(
        page=1,
        page_size=10,
        start_time=None,
        end_time=None,
        sale_no=None,
        current_employee_id=2,
        db=AsyncMock(spec=AsyncSession),
    )

    assert result.total == 1
    assert result.items[0].sale_no == "S202609010001"
    assert result.items[0].total_quantity == 3
    assert result.items[0].item_count == 2


async def test_sales_list_service_rejects_reversed_date_range(monkeypatch) -> None:
    """开始时间晚于结束时间时返回 400，且不查询销售数据。"""

    async def get_employee(**_kwargs):
        return build_employee()

    get_sales = AsyncMock()
    monkeypatch.setattr("app.services.sales.get_employee_by_id", get_employee)
    monkeypatch.setattr("app.services.sales.get_sales_list", get_sales)

    with pytest.raises(HTTPException) as exc_info:
        await get_sales_list_service(
            page=1,
            page_size=10,
            start_time=datetime(2026, 9, 2, 9, 0),
            end_time=datetime(2026, 9, 1, 21, 0),
            sale_no=None,
            current_employee_id=2,
            db=AsyncMock(spec=AsyncSession),
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "开始时间必须早于结束时间"
    get_sales.assert_not_awaited()


async def test_sales_list_service_rejects_time_outside_business_hours(monkeypatch) -> None:
    """查询时间早于 09:00 时返回 400。"""

    async def get_employee(**_kwargs):
        return build_employee()

    get_sales = AsyncMock()
    monkeypatch.setattr("app.services.sales.get_employee_by_id", get_employee)
    monkeypatch.setattr("app.services.sales.get_sales_list", get_sales)

    with pytest.raises(HTTPException) as exc_info:
        await get_sales_list_service(
            page=1,
            page_size=10,
            start_time=datetime(2026, 9, 1, 8, 0),
            end_time=datetime(2026, 9, 1, 12, 0),
            sale_no=None,
            current_employee_id=2,
            db=AsyncMock(spec=AsyncSession),
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "开始时间必须在09:00至21:00之间"
    get_sales.assert_not_awaited()


# endregion


# region 路由测试
def test_sales_list_route_returns_documented_response(monkeypatch) -> None:
    """销售单列表接口使用统一响应格式。"""

    async def get_sales(**_kwargs):
        return SalesListResponse(
            items=[],
            page=1,
            page_size=10,
            total=0,
            total_pages=0,
        )

    monkeypatch.setattr("app.routers.sales.get_sales_list_service", get_sales)
    application = create_app()
    application.dependency_overrides[get_db] = override_db
    application.dependency_overrides[get_current_employee_id] = override_employee_id

    with TestClient(application) as client:
        response = client.get("/api/v1/sales/list")

    assert response.status_code == 200
    assert response.json() == {
        "code": 200,
        "message": "获取销售单列表成功",
        "data": {
            "items": [],
            "page": 1,
            "page_size": 10,
            "total": 0,
            "total_pages": 0,
        },
    }


# endregion
