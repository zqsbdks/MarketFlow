"""基于 Redis 的跨进程短期分布式锁。"""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import uuid4

from app.core.redis import get_redis_client

logger = logging.getLogger(__name__)

_RELEASE_SCRIPT = """
if redis.call('get', KEYS[1]) == ARGV[1] then
  return redis.call('del', KEYS[1])
end
return 0
"""


@asynccontextmanager
async def distributed_lock(name: str, ttl_seconds: int) -> AsyncIterator[bool]:
    """尝试取得分布式锁；未配置 Redis 时允许单调度进程继续运行。"""

    client = get_redis_client()
    if client is None:
        yield True
        return

    key = f"marketflow:lock:{name}"
    token = uuid4().hex
    try:
        acquired = bool(await client.set(key, token, nx=True, ex=ttl_seconds))
    except Exception:
        # Redis 已配置却不可用时跳过任务，防止多个实例失去互斥后同时写库。
        logger.exception("取得分布式锁失败：%s", name)
        yield False
        return

    try:
        yield acquired
    finally:
        if acquired:
            try:
                await client.eval(_RELEASE_SCRIPT, 1, key, token)
            except Exception:
                # 锁仍会在 TTL 到期后自动释放，不阻止进程退出。
                logger.exception("释放分布式锁失败：%s", name)


__all__ = ["distributed_lock"]
