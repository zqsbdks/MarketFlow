"""营业报表的数据访问函数。"""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.category import Category
from app.models.department import Department
from app.models.enums import RankingGroupBy, RankingSortBy, RankingSortOrder
from app.models.product import Product
from app.models.sale import Sale
from app.models.sale_item import SaleItem

ReportValues = tuple[Decimal, Decimal, Decimal, int, int]
DepartmentReportValues = tuple[int, str, Decimal, Decimal, int]
RankingValues = tuple[int, str, int, Decimal]


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


async def get_departments_reports(
    db: AsyncSession,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
) -> list[DepartmentReportValues]:
    """一次查询所有部门的营收、毛利润和销售数量。"""

    # 先按部门汇总符合时间条件的销售明细。
    department_summary_statement = (
        select(
            SaleItem.department_id.label("department_id"),
            func.sum(SaleItem.subtotal).label("revenue"),
            func.sum(SaleItem.subtotal - SaleItem.cost_subtotal).label("gross_profit"),
            func.sum(SaleItem.quantity).label("sales_quantity"),
        )
        .join(Sale, Sale.id == SaleItem.sale_id)
        .group_by(SaleItem.department_id)
    )

    if start_time is not None:
        department_summary_statement = department_summary_statement.where(
            Sale.sold_at >= start_time
        )
    if end_time is not None:
        department_summary_statement = department_summary_statement.where(Sale.sold_at <= end_time)

    department_summary = department_summary_statement.subquery()

    # 从部门表开始做左连接，因此没有销售记录的部门也会返回，金额和数量为 0。
    statement = (
        select(
            Department.id,
            Department.name,
            func.coalesce(department_summary.c.revenue, 0),
            func.coalesce(department_summary.c.gross_profit, 0),
            func.coalesce(department_summary.c.sales_quantity, 0),
        )
        .outerjoin(
            department_summary,
            department_summary.c.department_id == Department.id,
        )
        .order_by(Department.id.asc())
    )

    result = await db.execute(statement)
    rows = result.all()

    departments: list[DepartmentReportValues] = []
    for department_id, department_name, revenue, gross_profit, sales_quantity in rows:
        department = (
            int(department_id),
            str(department_name),
            Decimal(revenue),
            Decimal(gross_profit),
            int(sales_quantity),
        )
        departments.append(department)

    return departments


# region 获取销售排行
async def get_rankings(
    db: AsyncSession,
    start_date: datetime | None,
    end_date: datetime | None,
    department_id: int | None,
    category_id: int | None,
    group_by: RankingGroupBy,
    sort_by: RankingSortBy,
    sort_order: RankingSortOrder,
    offset: int,
    page_size: int,
) -> tuple[list[RankingValues], int]:
    """按商品或分类汇总销售数据，并返回当前页和分组总数。"""

    conditions = []
    if start_date is not None:
        conditions.append(Sale.sold_at >= start_date)
    if end_date is not None:
        conditions.append(Sale.sold_at <= end_date)
    if department_id is not None:
        conditions.append(SaleItem.department_id == department_id)
    if category_id is not None:
        # 销售明细保存商品ID，通过商品所属分类筛选对应明细。
        product_ids = select(Product.id).where(Product.category_id == category_id)
        conditions.append(SaleItem.product_id.in_(product_ids))

    # 两种排行都需要计算累计销售数量和累计销售金额。
    total_quantity = func.sum(SaleItem.quantity).label("quantity")
    total_amount = func.sum(SaleItem.subtotal).label("amount")

    if group_by == RankingGroupBy.PRODUCT:
        list_statement = (
            select(
                Product.id,
                Product.name,
                total_quantity,
                total_amount,
            )
            .select_from(SaleItem)
            .join(Sale, Sale.id == SaleItem.sale_id)
            .join(Product, Product.id == SaleItem.product_id)
            .where(*conditions)
            .group_by(Product.id, Product.name)
        )
        count_statement = (
            select(func.count(distinct(SaleItem.product_id)))
            .select_from(SaleItem)
            .join(Sale, Sale.id == SaleItem.sale_id)
            .where(*conditions)
        )
        group_id = Product.id
    else:
        list_statement = (
            select(
                Category.id,
                Category.name,
                total_quantity,
                total_amount,
            )
            .select_from(SaleItem)
            .join(Sale, Sale.id == SaleItem.sale_id)
            .join(Product, Product.id == SaleItem.product_id)
            .join(Category, Category.id == Product.category_id)
            .where(*conditions)
            .group_by(Category.id, Category.name)
        )
        count_statement = (
            select(func.count(distinct(Category.id)))
            .select_from(SaleItem)
            .join(Sale, Sale.id == SaleItem.sale_id)
            .join(Product, Product.id == SaleItem.product_id)
            .join(Category, Category.id == Product.category_id)
            .where(*conditions)
        )
        group_id = Category.id

    # 根据请求选择数量或金额作为排序列，再选择升序或降序。
    sort_column = total_quantity if sort_by == RankingSortBy.QUANTITY else total_amount
    if sort_order == RankingSortOrder.ASC:
        order_expression = sort_column.asc()
    else:
        order_expression = sort_column.desc()

    list_statement = (
        list_statement.order_by(order_expression, group_id.asc()).offset(offset).limit(page_size)
    )

    total_result = await db.scalar(count_statement)
    list_result = await db.execute(list_statement)
    rows = list_result.all()

    rankings: list[RankingValues] = []
    for item_id, item_name, quantity, amount in rows:
        ranking = (
            int(item_id),
            str(item_name),
            int(quantity),
            Decimal(amount),
        )
        rankings.append(ranking)

    return rankings, int(total_result or 0)


# endregion


__all__ = [
    "DepartmentReportValues",
    "RankingValues",
    "ReportValues",
    "get_departments_reports",
    "get_rankings",
    "get_reports",
]
