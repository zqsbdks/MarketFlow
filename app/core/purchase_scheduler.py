"""进货单自动签收与库存批次状态刷新任务。

进货单每天 12:00 自动签收；临期状态每天 00:05 刷新；库存一致性检查在
营业时间内每半小时执行。各任务使用独立数据库事务，互不影响。
"""

import asyncio
import logging
from datetime import datetime, time, timedelta

from sqlalchemy import select

from app.core.business_time import business_now
from app.core.database import async_session_factory
from app.core.distributed_lock import distributed_lock
from app.crud.inventory_batches import refresh_inventory_batch_statuses
from app.crud.products import StockInconsistency, get_stock_inconsistencies
from app.crud.purchases import auto_receive_due_purchases
from app.models.inventory_batch import InventoryBatch
from app.models.purchase_plan import PurchasePlan
from app.services.inventory_discards import discard_expired_product
from app.services.purchase_plan_submission import submit_due_plan
from app.services.replenishment import refresh_automatic_plans

logger = logging.getLogger(__name__)
_last_replenishment_hour: datetime | None = None
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

    wait_seconds = max((run_time - business_now()).total_seconds(), 0)
    try:
        await asyncio.wait_for(stop_event.wait(), timeout=wait_seconds)
        return False
    except TimeoutError:
        return True


async def _run_auto_receive_once() -> int:
    """执行一次进货单自动签收，并提交本次数据库事务。"""

    async with distributed_lock("auto-receive", ttl_seconds=600) as acquired:
        if not acquired:
            logger.info("其他实例正在执行自动签收，本实例跳过")
            return 0
        now = business_now()
        cutoff = datetime.combine(now.date(), AUTO_RECEIVE_TIME)
        if now < cutoff:
            cutoff -= timedelta(days=1)
        async with async_session_factory() as db:
            try:
                purchases = await auto_receive_due_purchases(
                    arrived_at=cutoff,
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

    async with distributed_lock("batch-status-refresh", ttl_seconds=600) as acquired:
        if not acquired:
            logger.info("其他实例正在刷新批次状态，本实例跳过")
            return 0
        # 每个商品独立事务，锁顺序与销售相同，避免一次锁住全公司的库存。
        today = business_now().date()
        async with async_session_factory() as db:
            product_ids = list(
                (
                    await db.scalars(
                        select(InventoryBatch.product_id)
                        .where(
                            InventoryBatch.expiration_date < today,
                            InventoryBatch.remaining_quantity > 0,
                        )
                        .distinct()
                        .order_by(InventoryBatch.product_id)
                    )
                ).all()
            )
        discarded_count = 0
        for product_id in product_ids:
            async with async_session_factory() as db:
                try:
                    discarded_count += await discard_expired_product(product_id, today, db)
                    await db.commit()
                except Exception:
                    await db.rollback()
                    logger.exception("商品 %s 自动过期废弃失败，将在下次任务重试", product_id)
        logger.info("自动过期废弃完成，共处理 %s 个批次", discarded_count)
        async with async_session_factory() as db:
            try:
                changed_batch_count = await refresh_inventory_batch_statuses(
                    current_date=business_now().date(),
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
        next_run = _next_auto_receive_time(business_now())
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
        next_run = _next_batch_status_refresh_time(business_now())
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

    async with distributed_lock("stock-consistency", ttl_seconds=1500) as acquired:
        if not acquired:
            logger.info("其他实例正在检查库存一致性，本实例跳过")
            return []
        async with async_session_factory() as db:
            return await get_stock_inconsistencies(db=db)


async def _run_stock_consistency_scheduler(stop_event: asyncio.Event) -> None:
    """营业时间内每半小时检查库存一致性，只记录日志而不修复。"""

    while not stop_event.is_set():
        next_run = _next_stock_consistency_check_time(business_now())
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
    """并行运行截止下单、自动签收、过期/临期处理及营业时间内库存一致性检查。

    启动先补处理到期任务；后台异常记录日志，后续周期重试。
    stop_event用于生命周期退出，任务使用独立会话并自行提交，不复用HTTP请求会话。
    此调度器不包含联络事项关闭任务；联络事项有独立调度器。
    """

    # 进程曾在计划时间停机时，启动后补处理到期的进货单与批次状态。
    try:
        await _run_plan_submission_once()
    except Exception:
        logger.exception("启动订货计划补提交失败")
    try:
        await _run_auto_receive_once()
    except Exception:
        logger.exception("启动补签收失败；每日计划任务仍将继续运行")
    try:
        await _run_batch_status_refresh_once()
    except Exception:
        logger.exception("启动批次状态补刷新失败；每日计划任务仍将继续运行")
    await asyncio.gather(
        _run_plan_submission_scheduler(stop_event),
        _run_auto_receive_scheduler(stop_event),
        _run_batch_status_scheduler(stop_event),
        _run_stock_consistency_scheduler(stop_event),
    )


async def _run_plan_submission_once() -> int:
    global _last_replenishment_hour
    async with distributed_lock("purchase-plan-submit", ttl_seconds=600) as acquired:
        if not acquired:
            return 0
        now = business_now()
        hour = now.replace(minute=0, second=0, microsecond=0)
        if hour != _last_replenishment_hour:
            async with async_session_factory() as db:
                await refresh_automatic_plans(db, now)
            _last_replenishment_hour = hour
        latest = now.date() + timedelta(days=2 if now.time() >= AUTO_RECEIVE_TIME else 1)
        async with async_session_factory() as db:
            ids = list(
                (
                    await db.scalars(
                        select(PurchasePlan.id)
                        .where(
                            PurchasePlan.purchase_id.is_(None),
                            PurchasePlan.arrival_date <= latest,
                        )
                        .order_by(PurchasePlan.id)
                    )
                ).all()
            )
        count = 0
        for plan_id in ids:
            async with async_session_factory() as db:
                try:
                    count += int(await submit_due_plan(plan_id, db, now))
                    await db.commit()
                except Exception:
                    await db.rollback()
                    logger.exception("订货计划 %s 自动提交失败，下分钟重试", plan_id)
        return count


async def _run_plan_submission_scheduler(stop_event: asyncio.Event) -> None:
    # 整分钟检查：12:00 提交当天截止的计划，失败和停机后均可补处理。
    while not stop_event.is_set():
        next_run = business_now().replace(second=0, microsecond=0) + timedelta(minutes=1)
        if not await _wait_until(stop_event, next_run):
            break
        try:
            count = await _run_plan_submission_once()
            if count:
                logger.info("订货计划自动提交完成，共 %s 张进货单", count)
        except Exception:
            logger.exception("订货计划自动提交失败，下分钟重试")


__all__ = ["run_purchase_scheduler"]
