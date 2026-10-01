"""将浏览器 CSRF 令牌绑定到已签名的登录令牌。"""

import hashlib
import hmac

from app.core.config import settings


def csrf_for_session(token: str) -> str:
    """用服务端密钥生成不可伪造、无需额外保存的会话专属校验值。"""

    return hmac.new(
        settings.secret_key.encode("utf-8"), token.encode("utf-8"), hashlib.sha256
    ).hexdigest()


__all__ = ["csrf_for_session"]
