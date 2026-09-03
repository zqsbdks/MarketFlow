"""销售记录的数据访问函数。"""

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.sale import Sale


# region 获取销售单列表
async def get_sales_list(
    page: int,
    page_size: int,
    start_time: datetime | None,
    end_time: datetime | None,
    sale_no: str | None,
    db: AsyncSession,
) -> tuple[list[Sale], int]:
    """按条件分页查询销售单，并返回当前页销售单和总数。"""

    # 先创建不带筛选条件的基础查询。
    list_statement = select(Sale)
    count_statement = select(func.count(Sale.id))

    # 开始时间和结束时间都包含在查询范围内。
    if start_time is not None:
        list_statement = list_statement.where(Sale.sold_at >= start_time)
        count_statement = count_statement.where(Sale.sold_at >= start_time)

    if end_time is not None:
        list_statement = list_statement.where(Sale.sold_at <= end_time)
        count_statement = count_statement.where(Sale.sold_at <= end_time)

    # 销售单号使用唯一值精确查询。
    if sale_no is not None:
        list_statement = list_statement.where(Sale.sale_no == sale_no)
        count_statement = count_statement.where(Sale.sale_no == sale_no)

    count_result = await db.scalar(count_statement)
    total = count_result if count_result is not None else 0

    offset = (page - 1) * page_size
    list_statement = (
        list_statement.options(selectinload(Sale.items))
        .order_by(Sale.sold_at.desc(), Sale.id.desc())
        .offset(offset)
        .limit(page_size)
    )
    list_result = await db.scalars(list_statement)
    sales = list(list_result.all())

    return sales, total


# endregion


# region 根据销售单号获取详情
async def get_sales_detail(
    db: AsyncSession,
    sale_no: str,
) -> Sale | None:
    """根据唯一销售单号查询销售单，并提前加载商品明细。"""

    detail_statement = select(Sale).where(Sale.sale_no == sale_no).options(selectinload(Sale.items))
    detail_result = await db.scalar(detail_statement)
    return detail_result


# endregion


__all__ = ["get_sales_detail", "get_sales_list"]
