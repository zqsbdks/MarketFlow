"""进货单自动签收与库存批次状态刷新任务。

进货单每天 12:00 自动签收；临期状态每天 00:05 刷新；库存一致性检查在
营业时间内每半小时执行。各任务使用独立数据库事务，互不影响。
"""

import asyncio
import logging
from datetime import datetime, time, timedelta

from app.core.database import async_session_factory
from app.crud.inventory_batches import refresh_inventory_batch_statuses
from app.crud.products import StockInconsistency, get_stock_inconsistencies
from app.crud.purchases import auto_receive_due_purchases

logger = logging.getLogger(__name__)
AUTO_RECEIVE_TIME = time(hour=12)
STOCK_CONSISTENCY_CHECK_MINUTES = 30
BUSINESS_OPENING_TIME = time(hour=9)
BUSINESS_CLOSING_TIME = time(hour=21)
BATCH_STATUS_REFRESH_TIME = time(hour=0, minute=5)


def _next_auto_receive_time(now: datetime) -> datetime:
    """根据当前时间计算下一次自动签收进货单的时间。"""

    next_run = datetime.combine(now.date(), AUTO_RECEIVE_TIME)
    if next_run <= now:
        next_run += timedelta(days=1)
    return next_run


def _next_stock_consistency_check_time(now: datetime) -> datetime:
    """计算营业时间内的下一个库存一致性检查时间。

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
    if now.minute < STOCK_CONSISTENCY_CHECK_MINUTES:
        return now.replace(
            minute=STOCK_CONSISTENCY_CHECK_MINUTES,
            second=0,
            microsecond=0,
        )
    return now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)


def _next_batch_status_refresh_time(now: datetime) -> datetime:
    """计算下一次凌晨 00:05 的批次临期状态刷新时间。"""

    next_run = datetime.combine(now.date(), BATCH_STATUS_REFRESH_TIME)
    if next_run <= now:
        next_run += timedelta(days=1)
    return next_run


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
            purchases = await auto_receive_due_purchases(
                arrived_at=datetime.now(),
                employee_id=None,
                db=db,
            )
            await db.commit()
            return len(purchases)
        except Exception:
            await db.rollback()
            raise


async def _run_batch_status_refresh_once() -> int:
    """根据新一天的日期刷新批次临期状态。"""

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
    """每天凌晨 00:05 刷新批次临期状态，直到应用关闭。"""

    while not stop_event.is_set():
        next_run = _next_batch_status_refresh_time(datetime.now())
        logger.info("下一次库存批次临期状态刷新时间：%s", next_run.isoformat(sep=" "))
        if not await _wait_until(stop_event, next_run):
            break

        try:
            changed_batch_count = await _run_batch_status_refresh_once()
            logger.info("库存批次临期状态刷新完成，共更新 %s 个批次", changed_batch_count)
        except Exception:
            # 单次失败只记录日志，第二天凌晨仍会再次执行。
            logger.exception("库存批次临期状态刷新失败")


async def _run_stock_consistency_check_once() -> list[StockInconsistency]:
    """只读查询商品总库存与批次库存不一致的数据。"""

    async with async_session_factory() as db:
        return await get_stock_inconsistencies(db=db)


async def _run_stock_consistency_scheduler(stop_event: asyncio.Event) -> None:
    """营业时间内每半小时检查库存一致性，只记录日志而不修复。"""

    while not stop_event.is_set():
        next_run = _next_stock_consistency_check_time(datetime.now())
        logger.info("下一次库存一致性检查时间：%s", next_run.isoformat(sep=" "))
        if not await _wait_until(stop_event, next_run):
            break

        try:
            inconsistencies = await _run_stock_consistency_check_once()
            if not inconsistencies:
                logger.info("商品总库存与批次剩余库存检查完成，未发现异常")
            else:
                logger.warning(
                    "发现 %s 个商品库存不一致，本次检查不会自动修复", len(inconsistencies)
                )
                for (
                    product_id,
                    product_no,
                    product_name,
                    product_stock,
                    batch_stock,
                ) in inconsistencies:
                    logger.warning(
                        "库存不一致：商品ID=%s，编号=%s，名称=%s，商品库存=%s，批次库存=%s，差异=%s",
                        product_id,
                        product_no,
                        product_name,
                        product_stock,
                        batch_stock,
                        product_stock - batch_stock,
                    )
        except Exception:
            logger.exception("库存一致性检查失败")


async def run_purchase_scheduler(stop_event: asyncio.Event) -> None:
    """同时运行自动签收、每日临期刷新和半小时库存一致性检查。"""

    await asyncio.gather(
        _run_auto_receive_scheduler(stop_event),
        _run_batch_status_scheduler(stop_event),
        _run_stock_consistency_scheduler(stop_event),
    )


__all__ = ["run_purchase_scheduler"]
