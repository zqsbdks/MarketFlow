"""验证 Argon2 密码处理和 JWT 签发/解析的核心安全行为。"""

import jwt

from app.core.config import settings
from app.core.security import hash_password, verify_password
from app.core.token import create_access_token


def test_password_hash_and_verify() -> None:
    """正确密码应通过，错误密码应被拒绝。"""

    password_hash = hash_password("correct-password")

    # 同时覆盖正向和反向分支，防止验证函数意外恒为 True。
    assert verify_password("correct-password", password_hash)
    assert not verify_password("wrong-password", password_hash)


def test_access_token_round_trip() -> None:
    """签发后的 JWT 应能用同一密钥解码，并包含 sub 与 exp。"""

    token = create_access_token({"sub": "test-user"})
    # 显式限制算法可以防止解码端接受攻击者指定的其他算法。
    payload = jwt.decode(
        token,
        settings.secret_key,
        algorithms=[settings.jwt_algorithm],
    )

    assert payload["sub"] == "test-user"
    assert "exp" in payload
