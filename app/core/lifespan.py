"""应用生命周期管理模块。

本模块定义 FastAPI 的生命周期上下文，在应用启动阶段初始化缓存并按配置创建后台任务，
在应用关闭阶段释放数据库与 Redis 连接池资源，避免连接泄漏。
"""

import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi_cache import FastAPICache

from app.core.cache import initialize_business_cache
from app.core.config import settings
from app.core.contact_notice_scheduler import run_contact_notice_scheduler
from app.core.database import async_engine
from app.core.purchase_scheduler import run_purchase_scheduler
from app.core.redis import close_redis


@asynccontextmanager  # 将包含 yield 的异步函数转换为异步上下文管理器。
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """在应用启动和关闭时管理资源生命周期。

    Args:
        app (FastAPI): 当前 FastAPI 应用实例。
    """
    # 即使当前函数未直接使用 app，保留该参数以符合 FastAPI lifespan 协议。
    _ = app

    # 测试或应用工厂重复启动时，先清除上一次生命周期留下的全局缓存配置。
    FastAPICache.reset()  # 重置缓存框架配置，不是删除 Redis 中的数据。

    # Redis 未配置或初始化失败时降级为进程内缓存，应用仍可启动。
    await initialize_business_cache()  # 等待缓存后端配置完成，再继续启动流程。

    # 后台任务使用独立数据库会话，负责联络事项、订货、签收和库存定时处理。
    scheduler_stop_event = asyncio.Event()  # 创建共享停止信号，初始为未设置状态。
    scheduler_task = None  # 尚未创建进货与库存调度任务。
    notice_scheduler_task = None  # 尚未创建联络事项调度任务。
    if settings.run_scheduler:  # 仅在配置允许当前 Web 进程运行调度器时创建任务。
        notice_scheduler_task = asyncio.create_task(
            run_contact_notice_scheduler(scheduler_stop_event),  # 定期关闭到期联络事项。
            name="contact-notice-close",  # 任务名称，仅用于识别和调试。
        )
        scheduler_task = asyncio.create_task(
            run_purchase_scheduler(scheduler_stop_event),  # 并发管理订货、签收和库存任务。
            name="purchase-auto-receive",  # 名称不限制该调度器的业务范围。
        )

    # yield 之前是启动阶段，之后是应用收到关闭信号后的清理阶段。
    yield  # 启动阶段完成；正常关闭时从这里继续执行下方清理代码。

    # 先停止定时任务，再释放数据库连接池，防止任务访问已关闭的连接。
    scheduler_stop_event.set()  # 通知两个调度器停止，不是强制取消任务。
    if scheduler_task is not None:  # 未启用调度器时跳过等待。
        await scheduler_task  # 等待进货与库存调度器及其内部任务退出。
    if notice_scheduler_task is not None:
        await notice_scheduler_task  # 等待联络事项调度器退出。

    # 先释放数据库连接，再关闭 Redis；两个操作均由客户端库保证幂等性。
    await async_engine.dispose()  # 释放数据库连接池，不删除数据库数据。
    await close_redis()  # 关闭 Redis 客户端连接，不停止 Redis 服务或清空数据。
    FastAPICache.reset()  # 清除本次生命周期留下的缓存框架配置。
