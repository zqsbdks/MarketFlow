"""应用生命周期管理模块。

本模块定义 FastAPI 的生命周期上下文，在应用启动阶段进行连通性检查与缓存框架初始化，
在应用关闭阶段释放数据库与 Redis 连接池资源，避免连接泄漏。
"""

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi_cache import FastAPICache

from app.core.cache import initialize_business_cache
from app.core.config import settings
from app.core.contact_notice_scheduler import run_contact_notice_scheduler
from app.core.database import async_engine
from app.core.purchase_scheduler import run_purchase_scheduler
from app.core.redis import close_redis


@asynccontextmanager
async def lifespan(app: FastAPI):
    """在应用启动和关闭时管理资源生命周期。

    Args:
        app (FastAPI): 当前 FastAPI 应用实例。
    """
    # 即使当前函数未直接使用 app，保留该参数以符合 FastAPI lifespan 协议。
    _ = app

    # 测试或应用工厂重复启动时，先清除上一次生命周期留下的全局缓存配置。
    FastAPICache.reset()

    # 未配置 APP_REDIS_URL 时返回 None，应用可以在无 Redis 环境下启动。
    await initialize_business_cache()

    # 后台任务使用独立数据库会话，每天12点签收进货单并刷新库存批次状态。
    scheduler_stop_event = asyncio.Event()
    scheduler_task = None
    notice_scheduler_task = None
    if settings.run_scheduler:
        notice_scheduler_task = asyncio.create_task(
            run_contact_notice_scheduler(scheduler_stop_event), name="contact-notice-close"
        )
        scheduler_task = asyncio.create_task(
            run_purchase_scheduler(scheduler_stop_event),
            name="purchase-auto-receive",
        )

    # yield 之前是启动阶段，之后是应用收到关闭信号后的清理阶段。
    yield

    # 先停止定时任务，再释放数据库连接池，防止任务访问已关闭的连接。
    scheduler_stop_event.set()
    if scheduler_task is not None:
        await scheduler_task
    if notice_scheduler_task is not None:
        await notice_scheduler_task

    # 先释放数据库连接，再关闭 Redis；两个操作均由客户端库保证幂等性。
    await async_engine.dispose()
    await close_redis()
    FastAPICache.reset()
