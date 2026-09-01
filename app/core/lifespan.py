"""应用生命周期管理模块。

本模块定义 FastAPI 的生命周期上下文，在应用启动阶段进行连通性检查与缓存框架初始化，
在应用关闭阶段释放数据库与 Redis 连接池资源，避免连接泄漏。
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi_cache import FastAPICache
from fastapi_cache.backends.redis import RedisBackend

from app.core.database import async_engine
from app.core.redis import close_redis, get_redis_client


@asynccontextmanager
async def lifespan(app: FastAPI):
    """在应用启动和关闭时管理资源生命周期。

    Args:
        app (FastAPI): 当前 FastAPI 应用实例。
    """
    # 即使当前函数未直接使用 app，保留该参数以符合 FastAPI lifespan 协议。
    _ = app

    # 未配置 APP_REDIS_URL 时返回 None，应用可以在无 Redis 环境下启动。
    client = get_redis_client()
    if client is not None:
        try:
            # 先验证连接，再把同一客户端交给 fastapi-cache，避免重复连接池。
            await client.ping()
            FastAPICache.init(RedisBackend(client), prefix="fastapi-cache")
        except Exception:
            # Redis 在基础模板中属于可选服务，连接失败只记录日志，不阻止 API 启动。
            import logging

            logging.getLogger(__name__).exception("Redis initialization failed")

    # yield 之前是启动阶段，之后是应用收到关闭信号后的清理阶段。
    yield

    # 先释放数据库连接，再关闭 Redis；两个操作均由客户端库保证幂等性。
    await async_engine.dispose()
    await close_redis()
