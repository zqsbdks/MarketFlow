"""应用依赖项的就绪状态检查。"""

import logging

from sqlalchemy import text

from app.core.config import settings
from app.core.database import async_engine
from app.core.redis import get_redis_client

logger = logging.getLogger(__name__)


async def check_readiness() -> dict[str, str]:
    """检查数据库与可选 Redis，并返回适合监控系统读取的状态。"""

    components = {"database": "ok", "redis": "disabled"}
    try:
        async with async_engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
    except Exception:
        logger.exception("Database readiness check failed")
        components["database"] = "error"

    if settings.redis_url:
        client = get_redis_client()
        try:
            if client is None:
                raise RuntimeError("Redis client was not initialized")
            await client.ping()
            components["redis"] = "ok"
        except Exception:
            logger.exception("Redis readiness check failed")
            components["redis"] = "error"

    components["status"] = "ok" if "error" not in components.values() else "error"
    return components


__all__ = ["check_readiness"]
