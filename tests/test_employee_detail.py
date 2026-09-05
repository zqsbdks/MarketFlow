"""员工详情接口的权限边界与响应测试，不连接真实数据库。"""

from datetime import date, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.dependencies.auth import get_current_employee_id
from app.dependencies.db import get_db
from app.main import create_app
from app.models.enums import EmployeeGender, EmployeeRole, EmploymentStatus
from app.schemas.employees_requests import EmployeeDetailUpdateRequest
from app.services import employees as service


@pytest.mark.asyncio
@pytest.mark.parametrize("manager", [True, False])
async def test_update_detail_permissions_and_commit(monkeypatch, manager):
    """验证操作人身份、离职日期补全和成功提交；普通员工无写入权限。"""
    actor = SimpleNamespace(
        is_active=True,
        must_change_password=False,
        role=EmployeeRole.STORE_MANAGER if manager else EmployeeRole.REGULAR_EMPLOYEE,
    )
    lookup_actor = AsyncMock(return_value=actor)
    monkeypatch.setattr(service, "get_employee_by_id", lookup_actor)
    monkeypatch.setattr(
        service,
        "get_employee_detail_by_id",
        AsyncMock(
            return_value=SimpleNamespace(
                employment_status=EmploymentStatus.EMPLOYED,
                separation_date=None,
            )
        ),
    )
    write = AsyncMock()
    monkeypatch.setattr(service, "update_employee_detail", write)
    refreshed = object()
    monkeypatch.setattr(service, "get_employee_detail_service", AsyncMock(return_value=refreshed))
    db = AsyncMock()
    request = EmployeeDetailUpdateRequest(
        gender=EmployeeGender.MALE,
        birth_date=date(2000, 1, 1),
        hire_date=date(2020, 1, 1),
        phone="12345",
        address="测试地址",
        employment_status=EmploymentStatus.RESIGNED,
    )
    if manager:
        result = await service.update_employee_detail_service(2, 1, request, db)
        assert result is refreshed
        assert write.await_args.kwargs["separation_date"] == date.today()
        assert write.await_args.kwargs["phone"] == "12345"
        db.commit.assert_awaited_once()
    else:
        with pytest.raises(HTTPException) as error:
            await service.update_employee_detail_service(2, 1, request, db)
        assert error.value.status_code == 403
        write.assert_not_awaited()
        db.commit.assert_not_awaited()
    lookup_actor.assert_awaited_once_with(employee_id=1, db=db)


def test_update_detail_accepts_json_body():
    """编辑详情的敏感资料通过 JSON 请求体传入，不放在 URL 查询参数里。"""
    operation = create_app().openapi()["paths"]["/api/v1/employees/{employee_id}"]["put"]
    assert "application/json" in operation["requestBody"]["content"]
    assert all(parameter["in"] != "query" for parameter in operation.get("parameters", []))


@pytest.mark.parametrize(
    ("actor", "target_id", "expected_status"),
    [
        (None, 1, 401),
        (SimpleNamespace(id=1, is_active=False), 1, 403),
        (SimpleNamespace(id=1, is_active=True, must_change_password=True), 1, 403),
        (
            SimpleNamespace(
                id=1,
                is_active=True,
                must_change_password=False,
                role=EmployeeRole.REGULAR_EMPLOYEE,
            ),
            2,
            403,
        ),
    ],
)
@pytest.mark.asyncio
async def test_detail_rejects_invalid_access(monkeypatch, actor, target_id, expected_status):
    """无效访问者和越权请求应在读取目标详情之前被拒绝。"""
    monkeypatch.setattr(service, "get_employee_by_id", AsyncMock(return_value=actor))
    lookup = AsyncMock()
    monkeypatch.setattr(service, "get_employee_detail_by_id", lookup)
    with pytest.raises(HTTPException) as error:
        await service.get_employee_detail_service(target_id, 1, AsyncMock())
    assert error.value.status_code == expected_status
    lookup.assert_not_awaited()


@pytest.mark.parametrize("is_manager", [False, True])
def test_detail_route_returns_public_fields(monkeypatch, is_manager):
    """本人可查看，店长可查看停用员工；无部门及可空资料正确序列化。"""
    actor = SimpleNamespace(
        id=1,
        is_active=True,
        must_change_password=False,
        role=EmployeeRole.STORE_MANAGER if is_manager else EmployeeRole.REGULAR_EMPLOYEE,
    )
    target_id = 2 if is_manager else 1
    employee = SimpleNamespace(
        id=target_id,
        employee_no=f"E{target_id:05d}",
        name="测试员工",
        role=actor.role,
        department_id=None,
        department=None,
        is_active=not is_manager,
        must_change_password=is_manager,
        last_login_at=None,
        password_hash="should-not-be-returned",
    )
    detail = SimpleNamespace(
        employee=employee,
        gender=EmployeeGender.UNSPECIFIED,
        phone=None,
        birth_date=None,
        hire_date=date(2026, 9, 1),
        address=None,
        employment_status=EmploymentStatus.EMPLOYED,
        separation_date=None,
        separation_reason=None,
        created_at=datetime(2026, 9, 1),
        updated_at=datetime(2026, 9, 1),
    )
    monkeypatch.setattr(service, "get_employee_by_id", AsyncMock(return_value=actor))
    monkeypatch.setattr(service, "get_employee_detail_by_id", AsyncMock(return_value=detail))
    app = create_app()
    app.dependency_overrides[get_current_employee_id] = lambda: 1

    async def override_db():
        yield AsyncMock()

    app.dependency_overrides[get_db] = override_db
    with TestClient(app) as client:
        response = client.get(f"/api/v1/employees/{target_id}")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["id"] == target_id
    assert data["department_name"] is None
    assert data["hire_date"] == "2026-09-01"
    assert data["is_active"] is (not is_manager)
    assert "password_hash" not in data


@pytest.mark.asyncio
async def test_detail_missing_returns_404(monkeypatch):
    """有查看权限但详情不存在时返回 404。"""
    actor = SimpleNamespace(
        is_active=True,
        must_change_password=False,
        role=EmployeeRole.STORE_MANAGER,
    )
    monkeypatch.setattr(service, "get_employee_by_id", AsyncMock(return_value=actor))
    monkeypatch.setattr(service, "get_employee_detail_by_id", AsyncMock(return_value=None))
    with pytest.raises(HTTPException) as error:
        await service.get_employee_detail_service(999, 1, AsyncMock())
    assert error.value.status_code == 404
