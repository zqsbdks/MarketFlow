"""JWT 访问令牌签发工具。"""

from datetime import UTC, datetime, timedelta
from typing import Any

import jwt

from app.core.config import settings


def create_access_token(data: dict[str, Any], expires_delta: timedelta | None = None) -> str:
    """复制载荷、补充过期时间并签发 JWT。

    Args:
        data: 要写入令牌的声明，通常至少包含字符串形式的 ``sub``。
        expires_delta: 可选的自定义有效期；不传时使用全局分钟配置。

    Returns:
        str: 使用配置密钥和算法签名后的 JWT 字符串。
    """

    # 使用带时区的 UTC 时间，避免不同服务器时区造成过期判断不一致。
    expires = datetime.now(UTC) + (
        expires_delta or timedelta(minutes=settings.access_token_expire_minutes)
    )
    # 展开为新字典，防止给调用方传入的 data 原地增加 exp 字段。
    payload = {**data, "exp": expires}
    return jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)
