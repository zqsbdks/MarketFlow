"""进货单自动签收定时任务，每天本地时间12:00运行。"""

import asyncio
import logging
from datetime import datetime, time, timedelta

from app.core.database import async_session_factory
from app.crud.purchases import auto_receive_due_purchases

logger = logging.getLogger(__name__)
AUTO_RECEIVE_TIME = time(hour=12)


def _next_run_time(now: datetime) -> datetime:
    """根据当前时间计算下一次中午12点的执行时间。"""

    next_run = datetime.combine(now.date(), AUTO_RECEIVE_TIME)
    if next_run <= now:
        next_run += timedelta(days=1)
    return next_run


async def _run_auto_receive_once() -> int:
    """使用独立数据库会话执行一次到期进货单批量签收。"""

    async with async_session_factory() as db:
        try:
            purchases = await auto_receive_due_purchases(arrived_at=datetime.now(), db=db)
            await db.commit()
            return len(purchases)
        except Exception:
            await db.rollback()
            raise


async def run_purchase_scheduler(stop_event: asyncio.Event) -> None:
    """等待每日12点执行签收，并在应用关闭时安全停止。"""

    while not stop_event.is_set():
        now = datetime.now()
        next_run = _next_run_time(now)
        wait_seconds = max((next_run - now).total_seconds(), 0)
        logger.info("下一次进货单自动签收时间：%s", next_run.isoformat(sep=" "))
        try:
            # 同时等待执行时间和关闭信号，应用关闭时不必等到第二天。
            await asyncio.wait_for(stop_event.wait(), timeout=wait_seconds)
            continue
        except TimeoutError:
            pass

        try:
            received_count = await _run_auto_receive_once()
            logger.info("进货单自动签收完成，共签收 %s 张", received_count)
        except Exception:
            # 一次失败不终止循环；店长可补执行，次日任务也会继续运行。
            logger.exception("进货单自动签收失败")


__all__ = ["run_purchase_scheduler"]
