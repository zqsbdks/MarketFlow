"""营业报表的数据访问函数。"""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.sale import Sale
from app.models.sale_item import SaleItem

ReportValues = tuple[Decimal, Decimal, Decimal, int, int]


# region 获取营业概览
async def get_reports(
    db: AsyncSession,
    start_time: datetime | None,
    end_time: datetime | None,
    department_id: int | None,
) -> ReportValues:
    """查询整个店铺或指定部门的营业汇总数据。"""

    if department_id is None:
        # 全店金额直接汇总销售单，避免关联销售明细后重复计算订单金额。
        summary_statement = select(
            func.coalesce(func.sum(Sale.total_amount), 0),
            func.coalesce(func.sum(Sale.total_cost), 0),
            func.coalesce(func.sum(Sale.gross_profit), 0),
            func.count(Sale.id),
        )

        if start_time is not None:
            summary_statement = summary_statement.where(Sale.sold_at >= start_time)
        if end_time is not None:
            summary_statement = summary_statement.where(Sale.sold_at <= end_time)

        summary_result = await db.execute(summary_statement)
        revenue, sales_cost, gross_profit, sale_count = summary_result.one()

        # 商品数量位于销售明细表，通过所属销售单按销售时间筛选。
        quantity_statement = select(func.coalesce(func.sum(SaleItem.quantity), 0)).join(
            Sale, Sale.id == SaleItem.sale_id
        )
        if start_time is not None:
            quantity_statement = quantity_statement.where(Sale.sold_at >= start_time)
        if end_time is not None:
            quantity_statement = quantity_statement.where(Sale.sold_at <= end_time)

        sales_quantity = await db.scalar(quantity_statement)

        return (
            Decimal(revenue),
            Decimal(sales_cost),
            Decimal(gross_profit),
            int(sales_quantity or 0),
            int(sale_count),
        )

    # 部门金额只汇总该部门的销售明细，不能计算订单内其他部门的商品。
    department_statement = (
        select(
            func.coalesce(func.sum(SaleItem.subtotal), 0),
            func.coalesce(func.sum(SaleItem.cost_subtotal), 0),
            func.coalesce(
                func.sum(SaleItem.subtotal - SaleItem.cost_subtotal),
                0,
            ),
            func.coalesce(func.sum(SaleItem.quantity), 0),
            func.count(distinct(SaleItem.sale_id)),
        )
        .join(Sale, Sale.id == SaleItem.sale_id)
        .where(SaleItem.department_id == department_id)
    )

    if start_time is not None:
        department_statement = department_statement.where(Sale.sold_at >= start_time)
    if end_time is not None:
        department_statement = department_statement.where(Sale.sold_at <= end_time)

    department_result = await db.execute(department_statement)
    revenue, sales_cost, gross_profit, sales_quantity, sale_count = department_result.one()

    return (
        Decimal(revenue),
        Decimal(sales_cost),
        Decimal(gross_profit),
        int(sales_quantity),
        int(sale_count),
    )


# endregion


__all__ = ["ReportValues", "get_reports"]
