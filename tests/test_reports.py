"""营业概览 Service 与 API 测试。"""

from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies.auth import get_current_employee_id
from app.dependencies.db import get_db
from app.main import create_app
from app.schemas.reports_responses import ReportResponse
from app.services.reports import overview_service


def build_employee() -> SimpleNamespace:
    """构造允许查看营业数据的员工。"""

    return SimpleNamespace(is_active=True, must_change_password=False)


async def override_db():
    """路由测试使用空数据库依赖。"""

    yield None


async def override_employee_id() -> int:
    """路由测试固定当前员工ID。"""

    return 2


# region Service 测试
async def test_overview_service_returns_store_summary(monkeypatch) -> None:
    """未传部门ID时返回全店汇总。"""

    async def get_employee(**_kwargs):
        return build_employee()

    get_reports = AsyncMock(
        return_value=(
            Decimal("100.00"),
            Decimal("60.00"),
            Decimal("40.00"),
            7,
            3,
        )
    )
    monkeypatch.setattr("app.services.reports.get_employee_by_id", get_employee)
    monkeypatch.setattr("app.services.reports.get_reports", get_reports)

    result = await overview_service(
        db=AsyncMock(spec=AsyncSession),
        employee_id=2,
        start_time=None,
        end_time=None,
        department_id=None,
    )

    assert result.revenue == Decimal("100.00")
    assert result.sales_quantity == 7
    assert result.sale_count == 3
    assert get_reports.await_args.kwargs["department_id"] is None


async def test_overview_service_rejects_unknown_department(monkeypatch) -> None:
    """指定的部门不存在时返回404。"""

    async def get_employee(**_kwargs):
        return build_employee()

    async def get_department(**_kwargs):
        return None

    get_reports = AsyncMock()
    monkeypatch.setattr("app.services.reports.get_employee_by_id", get_employee)
    monkeypatch.setattr("app.services.reports.get_department_by_id", get_department)
    monkeypatch.setattr("app.services.reports.get_reports", get_reports)

    with pytest.raises(HTTPException) as exc_info:
        await overview_service(
            db=AsyncMock(spec=AsyncSession),
            employee_id=2,
            start_time=None,
            end_time=None,
            department_id=999,
        )

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "部门不存在"
    get_reports.assert_not_awaited()


async def test_overview_service_rejects_time_before_opening(monkeypatch) -> None:
    """开始时间早于09:00时不执行数据查询。"""

    async def get_employee(**_kwargs):
        return build_employee()

    get_reports = AsyncMock()
    monkeypatch.setattr("app.services.reports.get_employee_by_id", get_employee)
    monkeypatch.setattr("app.services.reports.get_reports", get_reports)

    with pytest.raises(HTTPException) as exc_info:
        await overview_service(
            db=AsyncMock(spec=AsyncSession),
            employee_id=2,
            start_time=datetime(2026, 9, 1, 8, 59),
            end_time=datetime(2026, 9, 1, 12, 0),
            department_id=None,
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "开始时间必须在 09:00 至 21:00 之间"
    get_reports.assert_not_awaited()


# endregion


# region 路由测试
def test_overview_route_returns_documented_response(monkeypatch) -> None:
    """营业概览接口返回项目统一响应格式。"""

    received: dict[str, object] = {}

    async def get_overview(**kwargs):
        received.update(kwargs)
        return ReportResponse(
            revenue=Decimal("100.00"),
            sales_cost=Decimal("60.00"),
            gross_profit=Decimal("40.00"),
            sales_quantity=7,
            sale_count=3,
        )

    monkeypatch.setattr("app.routers.reports.overview_service", get_overview)
    application = create_app()
    application.dependency_overrides[get_db] = override_db
    application.dependency_overrides[get_current_employee_id] = override_employee_id

    with TestClient(application) as client:
        response = client.get(
            "/api/v1/reports/overview",
            params={"department_id": 1},
        )

    assert response.status_code == 200
    assert received["department_id"] == 1
    assert response.json() == {
        "code": 200,
        "message": "获取营业概览数据成功",
        "data": {
            "revenue": "100.00",
            "sales_cost": "60.00",
            "gross_profit": "40.00",
            "sales_quantity": 7,
            "sale_count": 3,
        },
    }


# endregion
