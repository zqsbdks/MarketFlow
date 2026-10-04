"""独立运行门店定时任务；生产环境仅启动一个此进程。"""

import asyncio
import signal

from app.core.cache import initialize_business_cache
from app.core.database import async_engine
from app.core.purchase_scheduler import run_purchase_scheduler
from app.core.redis import close_redis


async def main() -> None:
    """收到停止信号后等待当前任务结束，再关闭数据库连接池。"""

    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for signum in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(signum, stop_event.set)
    try:
        await initialize_business_cache()
        await run_purchase_scheduler(stop_event)
    finally:
        await close_redis()
        await async_engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
