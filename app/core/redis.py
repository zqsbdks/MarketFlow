"""可选 Redis 异步客户端的创建、复用与关闭逻辑。"""

import logging
from typing import Any

from redis import asyncio as aioredis

from app.core.config import settings

logger = logging.getLogger(__name__)

# 模块级引用保证 FastAPI Cache 和其他依赖共享同一个 Redis 连接池。
redis_client: Any | None = None


def get_redis_client() -> Any | None:
    """按需创建并返回 Redis 客户端。

    Returns:
        Any | None: 已配置时返回可复用的异步客户端，否则返回 ``None``。
    """

    global redis_client
    if redis_client is None and settings.redis_url:
        # from_url 只构造客户端，真实连接在第一次命令（例如 ping）时建立。
        redis_client = aioredis.from_url(
            settings.redis_url,
            decode_responses=True,
            max_connections=settings.redis_max_connections,
            socket_timeout=settings.redis_timeout,
        )
    return redis_client


async def close_redis() -> None:
    """关闭 Redis 连接池，并清空模块级引用以支持后续重新初始化。"""
    global redis_client
    if redis_client is None:
        # 未启用 Redis 或已经关闭时无需执行任何操作。
        return
    try:
        await redis_client.aclose()
        logger.info("Redis connection pool closed")
    except Exception:
        logger.exception("Failed to close the Redis connection pool")
    finally:
        redis_client = None
