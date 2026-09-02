"""员工登录 Service 与 API 响应测试。"""

from unittest.mock import AsyncMock

import jwt
import pytest
from fastapi import HTTPException, status
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import hash_password, verify_password
from app.core.token import create_access_token
from app.dependencies.auth import get_current_token_payload
from app.dependencies.db import get_db
from app.main import create_app
from app.models.department import Department
from app.models.employee import Employee
from app.models.enums import EmployeeRole
from app.schemas.auth_responses import (
    AuthDepartmentResponse,
    AuthLoginEmployee,
    AuthLoginResponse,
    AuthMeResponse,
)
from app.services.auth import (
    auth_login_service,
    change_password_service,
    get_current_employee_info_service,
)


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
            department=None,
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
        "department": None,
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
    department = Department(id=1, code="MEAT", name="精肉部", is_active=True)
    employee.department_id = department.id
    employee.department = department

    async def get_employee(**_kwargs):
        return employee

    monkeypatch.setattr("app.services.auth.get_employee_by_employee_no", get_employee)
    session = AsyncMock(spec=AsyncSession)

    result = await auth_login_service("E00001", "correct-password", session)

    assert result.token_type == "bearer"
    assert result.employee.employee_no == employee.employee_no
    assert result.employee.department is not None
    assert result.employee.department.id == department.id
    assert result.employee.department.name == department.name
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


def test_get_current_employee_info_returns_documented_response(monkeypatch) -> None:
    """当前员工接口返回统一外层和嵌套部门信息。"""

    async def current_token_payload():
        return {"sub": "1"}

    async def get_employee_info(**_kwargs):
        return AuthMeResponse(
            id=1,
            employee_no="E00001",
            name="店长",
            role=EmployeeRole.STORE_MANAGER,
            department=AuthDepartmentResponse(id=1, name="精肉部"),
            is_active=True,
        )

    monkeypatch.setattr("app.routers.auth.get_current_employee_info_service", get_employee_info)
    application = create_app()
    application.dependency_overrides[get_db] = override_db
    application.dependency_overrides[get_current_token_payload] = current_token_payload

    with TestClient(application) as client:
        response = client.get("/api/v1/auth/me")

    assert response.status_code == 200
    assert response.json() == {
        "code": 200,
        "message": "获取当前登录员工信息成功",
        "data": {
            "id": 1,
            "employee_no": "E00001",
            "name": "店长",
            "role": "store_manager",
            "department": {"id": 1, "name": "精肉部"},
            "is_active": True,
        },
    }


async def test_get_current_employee_info_service_builds_response(monkeypatch) -> None:
    """Service 将员工及部门模型转换为当前员工响应。"""

    department = Department(id=1, code="MEAT", name="精肉部", is_active=True)
    employee = build_employee()
    employee.department_id = department.id
    employee.department = department

    async def get_employee(**_kwargs):
        return employee

    monkeypatch.setattr("app.services.auth.get_employee_by_id", get_employee)
    result = await get_current_employee_info_service(1, AsyncMock(spec=AsyncSession))

    assert result.id == employee.id
    assert result.department is not None
    assert result.department.id == department.id
    assert result.department.name == department.name


async def test_get_current_employee_info_service_rejects_missing_employee(monkeypatch) -> None:
    """Token 对应的员工不存在时返回 404。"""

    async def get_employee(**_kwargs):
        return None

    monkeypatch.setattr("app.services.auth.get_employee_by_id", get_employee)

    with pytest.raises(HTTPException) as exc_info:
        await get_current_employee_info_service(999, AsyncMock(spec=AsyncSession))

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "员工不存在"


def test_get_current_employee_info_rejects_non_numeric_subject() -> None:
    """Token 中的 sub 不是员工数字 ID 时返回 401。"""

    async def invalid_token_payload():
        return {"sub": "not-an-id"}

    application = create_app()
    application.dependency_overrides[get_db] = override_db
    application.dependency_overrides[get_current_token_payload] = invalid_token_payload

    with TestClient(application) as client:
        response = client.get("/api/v1/auth/me")

    assert response.status_code == 401
    assert response.json() == {
        "code": 401,
        "message": "访问令牌中的员工标识无效",
        "data": None,
    }


def test_change_password_returns_unified_response(monkeypatch) -> None:
    """修改密码接口成功时返回统一空数据响应。"""

    async def current_token_payload():
        return {"sub": "1"}

    change_service = AsyncMock(return_value=None)
    monkeypatch.setattr("app.routers.auth.change_password_service", change_service)
    application = create_app()
    application.dependency_overrides[get_db] = override_db
    application.dependency_overrides[get_current_token_payload] = current_token_payload

    with TestClient(application) as client:
        response = client.post(
            "/api/v1/auth/password",
            json={
                "old_password": "correct-password",
                "new_password": "new-password",
                "confirm_password": "new-password",
            },
        )

    assert response.status_code == 200
    assert response.json() == {
        "code": 200,
        "message": "密码修改成功",
        "data": None,
    }
    change_service.assert_awaited_once()


async def test_change_password_service_updates_hash_and_flag(monkeypatch) -> None:
    """密码修改成功后保存新哈希并取消首次修改标记。"""

    employee = build_employee()

    async def get_employee(**_kwargs):
        return employee

    monkeypatch.setattr("app.services.auth.get_employee_by_id", get_employee)
    session = AsyncMock(spec=AsyncSession)

    await change_password_service(
        employee_id=employee.id,
        old_password="correct-password",
        new_password="new-password",
        confirm_password="new-password",
        db=session,
    )

    assert verify_password("new-password", employee.password_hash)
    assert employee.must_change_password is False
    session.commit.assert_awaited_once()


@pytest.mark.parametrize(
    ("old_password", "new_password", "confirm_password", "expected_message"),
    [
        ("wrong-password", "new-password", "new-password", "旧密码错误"),
        ("correct-password", "new-password", "different-password", "两次输入的新密码不一致"),
        ("correct-password", "correct-password", "correct-password", "新密码不能与旧密码相同"),
    ],
)
async def test_change_password_service_rejects_invalid_passwords(
    monkeypatch,
    old_password: str,
    new_password: str,
    confirm_password: str,
    expected_message: str,
) -> None:
    """密码校验失败时不更新员工，也不提交事务。"""

    employee = build_employee()
    original_hash = employee.password_hash

    async def get_employee(**_kwargs):
        return employee

    monkeypatch.setattr("app.services.auth.get_employee_by_id", get_employee)
    session = AsyncMock(spec=AsyncSession)

    with pytest.raises(HTTPException) as exc_info:
        await change_password_service(
            employee_id=employee.id,
            old_password=old_password,
            new_password=new_password,
            confirm_password=confirm_password,
            db=session,
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == expected_message
    assert employee.password_hash == original_hash
    assert employee.must_change_password is True
    session.commit.assert_not_awaited()


def test_change_password_rejects_non_numeric_subject() -> None:
    """修改密码时 Token 中的员工 ID 无效则返回 401。"""

    async def invalid_token_payload():
        return {"sub": "not-an-id"}

    application = create_app()
    application.dependency_overrides[get_db] = override_db
    application.dependency_overrides[get_current_token_payload] = invalid_token_payload

    with TestClient(application) as client:
        response = client.post(
            "/api/v1/auth/password",
            json={
                "old_password": "correct-password",
                "new_password": "new-password",
                "confirm_password": "new-password",
            },
        )

    assert response.status_code == 401
    assert response.json()["message"] == "访问令牌中的员工标识无效"
