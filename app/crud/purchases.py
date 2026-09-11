"""进货管理的数据访问函数。"""

from datetime import date, datetime, time, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.sql.elements import ColumnElement

from app.models.enums import PurchaseStatus
from app.models.purchase import Purchase
from app.models.purchase_item import PurchaseItem


# region 获取进货单列表
async def get_all_purchases(
    offset: int,
    page_size: int,
    purchase_no: str | None,
    department_id: int | None,
    ordered_at: date | None,
    arrived_at: date | None,
    purchase_status: PurchaseStatus | None,
    db: AsyncSession,
) -> tuple[list[tuple[Purchase, int, int]], int]:
    """分页查询进货单，同时统计每张单的明细数和商品总数量。"""

    conditions: list[ColumnElement[bool]] = []
    if purchase_no is not None:
        # 两侧的%表示只要进货单号中包含关键字即可匹配。
        conditions.append(Purchase.purchase_no.ilike(f"%{purchase_no}%"))
    if department_id is not None:
        conditions.append(Purchase.department_id == department_id)
    if purchase_status is not None:
        conditions.append(Purchase.status == purchase_status)
    if ordered_at is not None:
        # 请求传入的是日期，查询范围从当天00:00到第二天00:00之前。
        day_start = datetime.combine(ordered_at, time.min)
        next_day_start = day_start + timedelta(days=1)
        conditions.append(Purchase.ordered_at >= day_start)
        conditions.append(Purchase.ordered_at < next_day_start)
    if arrived_at is not None:
        # arrived_at是实际到货时间；按日期查询时同样转换成一天的时间范围。
        arrival_day_start = datetime.combine(arrived_at, time.min)
        next_arrival_day_start = arrival_day_start + timedelta(days=1)
        conditions.append(Purchase.arrived_at >= arrival_day_start)
        conditions.append(Purchase.arrived_at < next_arrival_day_start)

    # 先按进货单分组统计明细行数和所有明细quantity之和。
    item_summary = (
        select(
            PurchaseItem.purchase_id.label("purchase_id"),
            func.count(PurchaseItem.id).label("item_count"),
            func.coalesce(func.sum(PurchaseItem.quantity), 0).label("total_quantity"),
        )
        .group_by(PurchaseItem.purchase_id)
        .subquery()
    )

    # 外连接统计结果，因此即使某张进货单暂时没有明细也仍然会出现在列表中。
    list_statement = (
        select(
            Purchase,
            func.coalesce(item_summary.c.item_count, 0),
            func.coalesce(item_summary.c.total_quantity, 0),
        )
        .outerjoin(item_summary, item_summary.c.purchase_id == Purchase.id)
        .options(
            selectinload(Purchase.department),
            selectinload(Purchase.created_by_employee),
            selectinload(Purchase.received_by_employee),
        )
        .where(*conditions)
        .order_by(Purchase.ordered_at.desc(), Purchase.id.desc())
        .offset(offset)
        .limit(page_size)
    )
    count_statement = select(func.count(Purchase.id)).where(*conditions)

    total = int(await db.scalar(count_statement) or 0)
    query_result = await db.execute(list_statement)

    purchases: list[tuple[Purchase, int, int]] = []
    for purchase, item_count, total_quantity in query_result.all():
        purchases.append((purchase, int(item_count), int(total_quantity)))
    return purchases, total


# endregion


# region 获取进货单详情
async def get_purchase_by_id(
    purchase_id: int,
    db: AsyncSession,
) -> Purchase | None:
    """根据ID查询进货单，并加载部门、员工和全部进货明细。"""

    statement = (
        select(Purchase)
        .options(
            selectinload(Purchase.department),
            selectinload(Purchase.created_by_employee),
            selectinload(Purchase.received_by_employee),
            selectinload(Purchase.items),
        )
        .where(Purchase.id == purchase_id)
    )
    result = await db.execute(statement)
    return result.scalar_one_or_none()


# endregion


__all__ = ["get_all_purchases", "get_purchase_by_id"]
