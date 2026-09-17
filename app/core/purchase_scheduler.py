"""进货单自动签收与库存批次状态刷新任务。

进货单仍在每天本地时间 12:00 自动签收；库存批次状态则在每个整点和
半点刷新一次。两个任务使用独立数据库事务，某一个任务失败不会停止另一个任务。
"""

import asyncio
import logging
from datetime import datetime, time, timedelta

from app.core.database import async_session_factory
from app.crud.inventory_batches import refresh_inventory_batch_statuses
from app.crud.purchases import auto_receive_due_purchases

logger = logging.getLogger(__name__)
AUTO_RECEIVE_TIME = time(hour=12)
BATCH_STATUS_REFRESH_MINUTES = 30
BUSINESS_OPENING_TIME = time(hour=9)
BUSINESS_CLOSING_TIME = time(hour=21)


def _next_auto_receive_time(now: datetime) -> datetime:
    """根据当前时间计算下一次自动签收进货单的时间。"""

    next_run = datetime.combine(now.date(), AUTO_RECEIVE_TIME)
    if next_run <= now:
        next_run += timedelta(days=1)
    return next_run


def _next_batch_status_refresh_time(now: datetime) -> datetime:
    """计算营业时间内的下一个整点或半点刷新时间。

    每天从 09:00 开始，每 30 分钟执行一次，21:00 执行当天最后一次；
    21:00 之后的下一次执行时间为第二天 09:00。
    """

    opening_at = datetime.combine(now.date(), BUSINESS_OPENING_TIME)
    closing_at = datetime.combine(now.date(), BUSINESS_CLOSING_TIME)

    # 营业前启动应用时，等待到当天 09:00 再执行。
    if now < opening_at:
        return opening_at

    # 21:00 的刷新已经结束或应用在闭店后启动，等待到第二天 09:00。
    if now >= closing_at:
        return opening_at + timedelta(days=1)

    # 营业期间把执行时间对齐到下一个整点或半点。
    if now.minute < BATCH_STATUS_REFRESH_MINUTES:
        return now.replace(
            minute=BATCH_STATUS_REFRESH_MINUTES,
            second=0,
            microsecond=0,
        )
    return now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)


async def _wait_until(stop_event: asyncio.Event, run_time: datetime) -> bool:
    """等待到指定时间；应用提前关闭时返回 False，到达时间时返回 True。"""

    wait_seconds = max((run_time - datetime.now()).total_seconds(), 0)
    try:
        await asyncio.wait_for(stop_event.wait(), timeout=wait_seconds)
        return False
    except TimeoutError:
        return True


async def _run_auto_receive_once() -> int:
    """执行一次进货单自动签收，并提交本次数据库事务。"""

    async with async_session_factory() as db:
        try:
            purchases = await auto_receive_due_purchases(arrived_at=datetime.now(), db=db)
            await db.commit()
            return len(purchases)
        except Exception:
            await db.rollback()
            raise


async def _run_batch_status_refresh_once() -> int:
    """执行一次库存批次状态刷新，并提交本次数据库事务。"""

    async with async_session_factory() as db:
        try:
            changed_batch_count = await refresh_inventory_batch_statuses(
                current_date=datetime.now().date(),
                db=db,
            )
            await db.commit()
            return changed_batch_count
        except Exception:
            await db.rollback()
            raise


async def _run_auto_receive_scheduler(stop_event: asyncio.Event) -> None:
    """每天 12:00 执行进货单自动签收，直到应用关闭。"""

    while not stop_event.is_set():
        next_run = _next_auto_receive_time(datetime.now())
        logger.info("下一次进货单自动签收时间：%s", next_run.isoformat(sep=" "))
        if not await _wait_until(stop_event, next_run):
            break

        try:
            received_count = await _run_auto_receive_once()
            logger.info("进货单自动签收完成，共签收 %s 张", received_count)
        except Exception:
            # 单次失败只记录日志，第二天仍会继续执行。
            logger.exception("进货单自动签收失败")


async def _run_batch_status_scheduler(stop_event: asyncio.Event) -> None:
    """营业时间内每个整点和半点刷新库存批次状态，直到应用关闭。"""

    while not stop_event.is_set():
        next_run = _next_batch_status_refresh_time(datetime.now())
        logger.info("下一次库存批次状态刷新时间：%s", next_run.isoformat(sep=" "))
        if not await _wait_until(stop_event, next_run):
            break

        try:
            changed_batch_count = await _run_batch_status_refresh_once()
            logger.info("库存批次状态刷新完成，共更新 %s 个批次", changed_batch_count)
        except Exception:
            # 单次失败只记录日志，半小时后仍会再次执行。
            logger.exception("库存批次状态刷新失败")


async def run_purchase_scheduler(stop_event: asyncio.Event) -> None:
    """同时运行每日自动签收任务和每半小时批次状态刷新任务。"""

    await asyncio.gather(
        _run_auto_receive_scheduler(stop_event),
        _run_batch_status_scheduler(stop_event),
    )


__all__ = ["run_purchase_scheduler"]
