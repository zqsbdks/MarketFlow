"""验证 JWT Bearer 认证依赖的成功与缺少凭据分支。"""

from datetime import timedelta

import jwt
import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from app.core.config import settings
from app.core.token import create_access_token
from app.dependencies.auth import get_current_token_payload


@pytest.mark.asyncio
async def test_current_token_payload_returns_token_payload() -> None:
    """有效令牌应通过签名校验并原样返回 sub 声明。"""

    # 使用正式签发函数生成令牌，覆盖签发与认证依赖之间的兼容性。
    token = create_access_token({"sub": "test-user"})
    credentials = HTTPAuthorizationCredentials(
        scheme="Bearer",
        credentials=token,
    )

    payload = await get_current_token_payload(credentials)

    assert payload["sub"] == "test-user"


@pytest.mark.asyncio
async def test_current_token_payload_rejects_missing_credentials() -> None:
    """缺少 Authorization 请求头时应返回 401。"""

    # 直接调用依赖函数，精确验证异常类型和状态码。
    with pytest.raises(HTTPException) as exc_info:
        await get_current_token_payload(None)

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
        await get_current_token_payload(credentials)

    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_current_token_payload_rejects_expired_token() -> None:
    """超过 exp 的令牌必须被拒绝。"""

    token = create_access_token({"sub": "test-user"}, expires_delta=timedelta(seconds=-1))
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)

    with pytest.raises(HTTPException) as exc_info:
        await get_current_token_payload(credentials)

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
        await get_current_token_payload(credentials)

    assert exc_info.value.status_code == 401
