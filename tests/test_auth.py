"""员工登录 Service 与 API 响应测试。"""

from unittest.mock import AsyncMock

import jwt
import pytest
from fastapi import HTTPException, status
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import hash_password
from app.core.token import create_access_token
from app.dependencies.db import get_db
from app.main import create_app
from app.models.employee import Employee
from app.models.enums import EmployeeRole
from app.schemas.auth_responses import AuthLoginEmployee, AuthLoginResponse
from app.services.auth import auth_login_service


def build_employee(*, is_active: bool = True) -> Employee:
    """构造不依赖数据库的店长测试对象。"""

    return Employee(
        id=1,
        employee_no="E00001",
        name="店长",
        password_hash=hash_password("correct-password"),
        role=EmployeeRole.STORE_MANAGER,
        department_id=None,
        department=None,
        is_active=is_active,
        must_change_password=True,
    )


async def override_db():
    """路由测试使用的占位数据库依赖。"""

    yield None


def build_login_result(employee: Employee) -> AuthLoginResponse:
    """构造路由测试使用的完整 Service 登录结果。"""

    return AuthLoginResponse(
        access_token=create_access_token({"sub": str(employee.id)}),
        token_type="bearer",
        employee=AuthLoginEmployee(
            id=employee.id,
            employee_no=employee.employee_no,
            name=employee.name,
            role=employee.role,
            department_id=employee.department_id,
            must_change_password=employee.must_change_password,
        ),
    )


def test_login_returns_documented_response(monkeypatch) -> None:
    """成功登录返回 bearer Token 和员工公开信息。"""

    employee = build_employee()

    async def login(**_kwargs):
        return build_login_result(employee)

    monkeypatch.setattr("app.routers.auth.auth_login_service", login)
    application = create_app()
    application.dependency_overrides[get_db] = override_db

    with TestClient(application) as client:
        response = client.post(
            "/api/v1/auth/login",
            json={"employee_no": "E00001", "password": "correct-password"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["message"] == "登录成功"
    assert body["data"]["token_type"] == "bearer"
    assert body["data"]["employee"] == {
        "id": 1,
        "employee_no": "E00001",
        "name": "店长",
        "role": "store_manager",
        "department_id": None,
        "must_change_password": True,
    }
    payload = jwt.decode(
        body["data"]["access_token"],
        settings.secret_key,
        algorithms=[settings.jwt_algorithm],
    )
    assert payload["sub"] == "1"


def test_login_rejects_invalid_credentials(monkeypatch) -> None:
    """不存在的员工或错误密码统一返回 401。"""

    async def login(**_kwargs):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="员工编号或密码错误",
            headers={"WWW-Authenticate": "Bearer"},
        )

    monkeypatch.setattr("app.routers.auth.auth_login_service", login)
    application = create_app()
    application.dependency_overrides[get_db] = override_db

    with TestClient(application) as client:
        response = client.post(
            "/api/v1/auth/login",
            json={"employee_no": "E99999", "password": "wrong-password"},
        )

    assert response.status_code == 401
    assert response.json() == {
        "code": 401,
        "message": "员工编号或密码错误",
        "data": None,
    }
    assert response.headers["www-authenticate"] == "Bearer"


def test_login_rejects_inactive_employee(monkeypatch) -> None:
    """密码正确但账号停用时返回 403。"""

    async def login(**_kwargs):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="账号已停用",
        )

    monkeypatch.setattr("app.routers.auth.auth_login_service", login)
    application = create_app()
    application.dependency_overrides[get_db] = override_db

    with TestClient(application) as client:
        response = client.post(
            "/api/v1/auth/login",
            json={"employee_no": "E00001", "password": "correct-password"},
        )

    assert response.status_code == 403
    assert response.json()["message"] == "账号已停用"


async def test_login_service_verifies_password_and_records_login(monkeypatch) -> None:
    """Service 只在有效账号密码登录时提交最后登录时间。"""

    employee = build_employee()

    async def get_employee(**_kwargs):
        return employee

    monkeypatch.setattr("app.services.auth.get_employee_by_employee_no", get_employee)
    session = AsyncMock(spec=AsyncSession)

    result = await auth_login_service("E00001", "correct-password", session)

    assert result.token_type == "bearer"
    assert result.employee.employee_no == employee.employee_no
    assert employee.last_login_at is not None
    session.flush.assert_awaited_once()
    session.commit.assert_awaited_once()


async def test_login_service_does_not_commit_wrong_password(monkeypatch) -> None:
    """错误密码不会更新或提交员工记录。"""

    employee = build_employee()

    async def get_employee(**_kwargs):
        return employee

    monkeypatch.setattr("app.services.auth.get_employee_by_employee_no", get_employee)
    session = AsyncMock(spec=AsyncSession)

    with pytest.raises(HTTPException) as exc_info:
        await auth_login_service("E00001", "wrong-password", session)

    assert exc_info.value.status_code == 401
    assert employee.last_login_at is None
    session.flush.assert_not_awaited()
    session.commit.assert_not_awaited()


async def test_login_service_does_not_commit_inactive_employee(monkeypatch) -> None:
    """停用账号返回 403，且不记录成功登录时间。"""

    employee = build_employee(is_active=False)

    async def get_employee(**_kwargs):
        return employee

    monkeypatch.setattr("app.services.auth.get_employee_by_employee_no", get_employee)
    session = AsyncMock(spec=AsyncSession)

    with pytest.raises(HTTPException) as exc_info:
        await auth_login_service("E00001", "correct-password", session)

    assert exc_info.value.status_code == 403
    assert employee.last_login_at is None
    session.flush.assert_not_awaited()
    session.commit.assert_not_awaited()
