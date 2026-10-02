"""验证 JWT Bearer 认证依赖的成功与缺少凭据分支。"""

from datetime import timedelta

import jwt
import pytest
from unittest.mock import AsyncMock
from fastapi import HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials

from app.core.config import settings
from app.core.csrf import csrf_for_session
from app.core.token import create_access_token
from app.dependencies.auth import get_current_employee_id, get_current_token_payload


def _request() -> Request:
    """构造不带 Cookie 的普通 GET 请求，覆盖 Bearer 兼容路径。"""

    return Request({"type": "http", "method": "GET", "headers": []})


@pytest.mark.asyncio
async def test_current_token_payload_returns_token_payload() -> None:
    """有效令牌应通过签名校验并原样返回 sub 声明。"""

    # 使用正式签发函数生成令牌，覆盖签发与认证依赖之间的兼容性。
    token = create_access_token({"sub": "test-user"})
    credentials = HTTPAuthorizationCredentials(
        scheme="Bearer",
        credentials=token,
    )

    payload = await get_current_token_payload(_request(), credentials)

    assert payload["sub"] == "test-user"


@pytest.mark.asyncio
async def test_current_token_payload_rejects_missing_credentials() -> None:
    """缺少 Authorization 请求头时应返回 401。"""

    # 直接调用依赖函数，精确验证异常类型和状态码。
    with pytest.raises(HTTPException) as exc_info:
        await get_current_token_payload(_request(), None)

    assert exc_info.value.status_code == 401
    assert exc_info.value.headers == {"WWW-Authenticate": "Bearer"}


@pytest.mark.asyncio
async def test_current_token_payload_rejects_missing_expiration() -> None:
    """即使签名正确，没有 exp 的永久令牌也必须被拒绝。"""

    token = jwt.encode(
        {"sub": "test-user"},
        settings.secret_key,
        algorithm=settings.jwt_algorithm,
    )
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)

    with pytest.raises(HTTPException) as exc_info:
        await get_current_token_payload(_request(), credentials)

    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_current_token_payload_rejects_expired_token() -> None:
    """超过 exp 的令牌必须被拒绝。"""

    token = create_access_token({"sub": "test-user"}, expires_delta=timedelta(seconds=-1))
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)

    with pytest.raises(HTTPException) as exc_info:
        await get_current_token_payload(_request(), credentials)

    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_current_token_payload_rejects_wrong_signature() -> None:
    """由其他密钥签发的令牌不得通过验证。"""

    token = jwt.encode(
        {"sub": "test-user", "exp": 4_102_444_800},
        "a-different-secret-key-that-is-long-enough",
        algorithm=settings.jwt_algorithm,
    )
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)

    with pytest.raises(HTTPException) as exc_info:
        await get_current_token_payload(_request(), credentials)

    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_cookie_auth_requires_matching_csrf_header_for_writes() -> None:
    """浏览器自动携带 Cookie 时，修改请求必须再提供 CSRF 令牌。"""

    token = create_access_token({"sub": "123"})
    csrf = csrf_for_session(token)
    cookie = f"marketflow_session={token}; marketflow_csrf={csrf}".encode()
    request = Request({"type": "http", "method": "POST", "headers": [(b"cookie", cookie)]})
    with pytest.raises(HTTPException) as exc_info:
        await get_current_token_payload(request, None)
    assert exc_info.value.status_code == 403

    valid_request = Request(
        {
            "type": "http",
            "method": "POST",
            "headers": [(b"cookie", cookie), (b"x-csrf-token", csrf.encode())],
        }
    )
    payload = await get_current_token_payload(valid_request, None)
    assert payload["sub"] == "123"


@pytest.mark.asyncio
async def test_current_employee_id_returns_integer(monkeypatch) -> None:
    """数字字符串形式的 sub 应转换为员工整数 ID。"""

    async def fake_employee(**_kwargs):
        return type("EmployeeStub", (), {"is_active": True})()
    monkeypatch.setattr("app.dependencies.auth.get_employee_by_id", fake_employee)
    monkeypatch.setattr("app.core.store_policy.configure_store_context", AsyncMock())
    employee_id = await get_current_employee_id(_request(), {"sub": "123"}, AsyncMock())

    assert employee_id == 123


@pytest.mark.asyncio
async def test_current_employee_id_rejects_non_numeric_subject() -> None:
    """无法转换为整数的 sub 应返回 401。"""

    with pytest.raises(HTTPException) as exc_info:
        await get_current_employee_id(_request(), {"sub": "not-an-id"}, AsyncMock())

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "访问令牌中的员工标识无效"
    assert exc_info.value.headers == {"WWW-Authenticate": "Bearer"}
