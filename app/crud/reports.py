"""营业报表的数据访问函数。"""

from datetime import date, datetime, time
from decimal import Decimal
from typing import Literal

from sqlalchemy import distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from app.core.cache import (
    REPORTS_CACHE_NAMESPACE,
    REPORTS_CACHE_SECONDS,
    business_cache,
    historical_report,
)
from app.models.category import Category
from app.models.department import Department
from app.models.enums import RankingGroupBy, RankingSortBy, RankingSortOrder
from app.models.product import Product
from app.models.sale import Sale
from app.models.sale_item import SaleItem
from app.models.store import StoreDepartment

ReportValues = tuple[Decimal, Decimal, Decimal, int, int]
DepartmentReportValues = tuple[int, str, Decimal, Decimal, int]
RankingValues = tuple[int, str, int, Decimal]
AnalyticsSummaryValues = tuple[Decimal, Decimal, Decimal, Decimal, Decimal, int, int]
AnalyticsTrendValues = tuple[
    datetime,
    Decimal,
    Decimal,
    Decimal,
    Decimal,
    Decimal,
    int,
    int,
]
AnalyticsDepartmentValues = tuple[int, str, Decimal]
AnalyticsValues = tuple[
    AnalyticsSummaryValues | None,
    list[AnalyticsDepartmentValues],
    list[AnalyticsTrendValues],
]


# region 获取营业概览
@business_cache(REPORTS_CACHE_NAMESPACE, REPORTS_CACHE_SECONDS, enabled=historical_report)
async def get_reports(
    db: AsyncSession,
    start_time: datetime | None,
    end_time: datetime | None,
    department_id: int | None,
) -> ReportValues:
    """查询整个店铺或指定部门的营业汇总数据。"""
    if department_id is None:
        summary_statement = select(
            func.coalesce(func.sum(Sale.total_amount), 0),
            func.coalesce(func.sum(Sale.total_cost), 0),
            func.coalesce(func.sum(Sale.gross_profit), 0),
            func.count(Sale.id),
        )
        if db.info.get("read_store_id") is not None:
            summary_statement = summary_statement.where(Sale.store_id == db.info["read_store_id"])
        if start_time is not None:
            summary_statement = summary_statement.where(Sale.sold_at >= start_time)
        if end_time is not None:
            summary_statement = summary_statement.where(Sale.sold_at <= end_time)
        summary_result = await db.execute(summary_statement)
        revenue, sales_cost, gross_profit, sale_count = summary_result.one()
        quantity_statement = select(func.coalesce(func.sum(SaleItem.quantity), 0)).join(
            Sale, Sale.id == SaleItem.sale_id
        )
        if db.info.get("read_store_id") is not None:
            quantity_statement = quantity_statement.where(
                SaleItem.store_id == db.info["read_store_id"]
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
    department_statement = (
        select(
            func.coalesce(func.sum(SaleItem.subtotal), 0),
            func.coalesce(func.sum(SaleItem.cost_subtotal), 0),
            func.coalesce(func.sum(SaleItem.subtotal - SaleItem.cost_subtotal), 0),
            func.coalesce(func.sum(SaleItem.quantity), 0),
            func.count(distinct(SaleItem.sale_id)),
        )
        .join(Sale, Sale.id == SaleItem.sale_id)
        .where(SaleItem.department_id == department_id)
    )
    if db.info.get("read_store_id") is not None:
        department_statement = department_statement.where(
            SaleItem.store_id == db.info["read_store_id"]
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


# region 获取部门营业对比
@business_cache(REPORTS_CACHE_NAMESPACE, REPORTS_CACHE_SECONDS, enabled=historical_report)
async def get_departments_reports(
    db: AsyncSession, start_time: datetime | None = None, end_time: datetime | None = None
) -> list[DepartmentReportValues]:
    """一次查询所有部门的营收、毛利润和销售数量。"""
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
    if db.info.get("read_store_id") is not None:
        department_summary_statement = department_summary_statement.where(
            SaleItem.store_id == db.info["read_store_id"]
        )
    if start_time is not None:
        department_summary_statement = department_summary_statement.where(
            Sale.sold_at >= start_time
        )
    if end_time is not None:
        department_summary_statement = department_summary_statement.where(Sale.sold_at <= end_time)
    department_summary = department_summary_statement.subquery()
    statement = (
        select(
            Department.id,
            Department.name,
            func.coalesce(department_summary.c.revenue, 0),
            func.coalesce(department_summary.c.gross_profit, 0),
            func.coalesce(department_summary.c.sales_quantity, 0),
        )
        .outerjoin(department_summary, department_summary.c.department_id == Department.id)
        .order_by(Department.id.asc())
    )
    if db.info.get("read_store_id") is not None and (not db.info.get("company_catalog_read")):
        enabled_departments = select(StoreDepartment.department_id).where(
            StoreDepartment.store_id == db.info["read_store_id"],
            StoreDepartment.is_active.is_(True),
        )
        statement = statement.where(Department.id.in_(enabled_departments))
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


# endregion


# region 获取销售排行
@business_cache(REPORTS_CACHE_NAMESPACE, REPORTS_CACHE_SECONDS, enabled=historical_report)
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
        product_ids = select(Product.id).where(Product.category_id == category_id)
        if db.info.get("read_store_id") is not None:
            product_ids = product_ids.where(Product.store_id == db.info["read_store_id"])
        conditions.append(SaleItem.product_id.in_(product_ids))
    total_quantity = func.sum(SaleItem.quantity).label("quantity")
    total_amount = func.sum(SaleItem.subtotal).label("amount")
    if group_by == RankingGroupBy.PRODUCT:
        list_statement = (
            select(Product.id, Product.name, total_quantity, total_amount)
            .select_from(SaleItem)
            .join(Sale, Sale.id == SaleItem.sale_id)
            .join(Product, Product.id == SaleItem.product_id)
            .where(*conditions)
            .group_by(Product.id, Product.name)
        )
        if db.info.get("read_store_id") is not None:
            list_statement = list_statement.where(Product.store_id == db.info["read_store_id"])
        if db.info.get("read_store_id") is not None:
            list_statement = list_statement.where(SaleItem.store_id == db.info["read_store_id"])
        count_statement = (
            select(func.count(distinct(SaleItem.product_id)))
            .select_from(SaleItem)
            .join(Sale, Sale.id == SaleItem.sale_id)
            .where(*conditions)
        )
        if db.info.get("read_store_id") is not None:
            count_statement = count_statement.where(SaleItem.store_id == db.info["read_store_id"])
        group_id = Product.id
    else:
        list_statement = (
            select(Category.id, Category.name, total_quantity, total_amount)
            .select_from(SaleItem)
            .join(Sale, Sale.id == SaleItem.sale_id)
            .join(Product, Product.id == SaleItem.product_id)
            .join(Category, Category.id == Product.category_id)
            .where(*conditions)
            .group_by(Category.id, Category.name)
        )
        if db.info.get("read_store_id") is not None:
            list_statement = list_statement.where(SaleItem.store_id == db.info["read_store_id"])
        if db.info.get("read_store_id") is not None and (not db.info.get("company_catalog_read")):
            enabled_departments = select(StoreDepartment.department_id).where(
                StoreDepartment.store_id == db.info["read_store_id"],
                StoreDepartment.is_active.is_(True),
            )
            list_statement = list_statement.where(Category.department_id.in_(enabled_departments))
        count_statement = (
            select(func.count(distinct(Category.id)))
            .select_from(SaleItem)
            .join(Sale, Sale.id == SaleItem.sale_id)
            .join(Product, Product.id == SaleItem.product_id)
            .join(Category, Category.id == Product.category_id)
            .where(*conditions)
        )
        if db.info.get("read_store_id") is not None:
            count_statement = count_statement.where(SaleItem.store_id == db.info["read_store_id"])
        if db.info.get("read_store_id") is not None and (not db.info.get("company_catalog_read")):
            enabled_departments = select(StoreDepartment.department_id).where(
                StoreDepartment.store_id == db.info["read_store_id"],
                StoreDepartment.is_active.is_(True),
            )
            count_statement = count_statement.where(Category.department_id.in_(enabled_departments))
        group_id = Category.id
    # 金额列和数量列的数据类型不同，但都可以作为 SQL 排序列。
    sort_column: ColumnElement
    if sort_by == RankingSortBy.QUANTITY:
        sort_column = total_quantity
    else:
        sort_column = total_amount
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
        ranking = (int(item_id), str(item_name), int(quantity), Decimal(amount))
        rankings.append(ranking)
    return (rankings, int(total_result or 0))


# endregion


# region 获取营业分析
@business_cache(REPORTS_CACHE_NAMESPACE, REPORTS_CACHE_SECONDS, enabled=historical_report)
async def get_report_analytics(
    db: AsyncSession,
    start_time: datetime,
    end_time: datetime,
    department_id: int | None,
    interval: Literal["hour", "day", "month", "year"],
    include_summary: bool,
    include_departments: bool,
    include_trend: bool,
) -> AnalyticsValues:
    """按勾选项查询营业汇总、部门营业额和时间趋势的原始数据。

    Args:
        db: 当前请求使用的异步数据库会话。
        start_time: 销售发生时间的查询下限，包含该时间。
        end_time: 销售发生时间的查询上限，不包含该时间。
        department_id: 部门ID；为None时不添加部门筛选条件。
        interval: 趋势分组粒度，支持小时、日、月和年。
        include_summary: 是否执行营业汇总查询。
        include_departments: 是否执行各部门营业额查询。
        include_trend: 是否执行按时间分组的趋势查询。

    Returns:
        AnalyticsValues: 依次返回汇总数据、部门数据列表和趋势数据列表。
    """
    base_conditions = [Sale.sold_at >= start_time, Sale.sold_at < end_time]
    if department_id is not None:
        base_conditions.append(SaleItem.department_id == department_id)
    summary: AnalyticsSummaryValues | None = None
    if include_summary:
        summary_statement = (
            select(
                func.coalesce(func.sum(SaleItem.original_unit_price * SaleItem.quantity), 0),
                func.coalesce(func.sum(SaleItem.subtotal), 0),
                func.coalesce(func.sum(SaleItem.discount_amount), 0),
                func.coalesce(func.sum(SaleItem.cost_subtotal), 0),
                func.coalesce(func.sum(SaleItem.subtotal - SaleItem.cost_subtotal), 0),
                func.coalesce(func.sum(SaleItem.quantity), 0),
                func.count(distinct(SaleItem.sale_id)),
            )
            .select_from(SaleItem)
            .join(Sale, Sale.id == SaleItem.sale_id)
            .where(*base_conditions)
        )
        if db.info.get("read_store_id") is not None:
            summary_statement = summary_statement.where(
                SaleItem.store_id == db.info["read_store_id"]
            )
        result = await db.execute(summary_statement)
        (
            original_revenue,
            revenue,
            discount_amount,
            sales_cost,
            gross_profit,
            sales_quantity,
            sale_count,
        ) = result.one()
        summary = (
            Decimal(original_revenue),
            Decimal(revenue),
            Decimal(discount_amount),
            Decimal(sales_cost),
            Decimal(gross_profit),
            int(sales_quantity),
            int(sale_count),
        )
    departments: list[AnalyticsDepartmentValues] = []
    if include_departments:
        store_query_12 = (
            select(
                SaleItem.department_id.label("department_id"),
                func.sum(SaleItem.subtotal).label("revenue"),
            )
            .select_from(SaleItem)
            .join(Sale, Sale.id == SaleItem.sale_id)
            .where(Sale.sold_at >= start_time, Sale.sold_at < end_time)
            .group_by(SaleItem.department_id)
        )
        if db.info.get("read_store_id") is not None:
            store_query_12 = store_query_12.where(SaleItem.store_id == db.info["read_store_id"])
        department_summary = store_query_12.subquery()
        department_statement = (
            select(Department.id, Department.name, func.coalesce(department_summary.c.revenue, 0))
            .select_from(Department)
            .outerjoin(department_summary, department_summary.c.department_id == Department.id)
            .order_by(Department.id)
        )
        if db.info.get("read_store_id") is not None and (not db.info.get("company_catalog_read")):
            enabled_departments = select(StoreDepartment.department_id).where(
                StoreDepartment.store_id == db.info["read_store_id"],
                StoreDepartment.is_active.is_(True),
            )
            department_statement = department_statement.where(
                Department.id.in_(enabled_departments)
            )
        department_result = await db.execute(department_statement)
        departments_values = []
        for departments_item_id, departments_name, departments_revenue in department_result.all():
            departments_values.append(
                (int(departments_item_id), str(departments_name), Decimal(departments_revenue))
            )
        departments = departments_values
    trend: list[AnalyticsTrendValues] = []
    if include_trend:
        if interval == "hour":
            bucket_expression = func.date_format(Sale.sold_at, "%Y-%m-%d %H:00:00")
        elif interval == "day":
            bucket_expression = func.date(Sale.sold_at)
        elif interval == "month":
            bucket_expression = func.date_format(Sale.sold_at, "%Y-%m-01 00:00:00")
        else:
            bucket_expression = func.date_format(Sale.sold_at, "%Y-01-01 00:00:00")
        trend_statement = (
            select(
                bucket_expression.label("bucket"),
                func.coalesce(func.sum(SaleItem.original_unit_price * SaleItem.quantity), 0),
                func.coalesce(func.sum(SaleItem.subtotal), 0),
                func.coalesce(func.sum(SaleItem.discount_amount), 0),
                func.coalesce(func.sum(SaleItem.cost_subtotal), 0),
                func.coalesce(func.sum(SaleItem.subtotal - SaleItem.cost_subtotal), 0),
                func.coalesce(func.sum(SaleItem.quantity), 0),
                func.count(distinct(SaleItem.sale_id)),
            )
            .select_from(SaleItem)
            .join(Sale, Sale.id == SaleItem.sale_id)
            .where(*base_conditions)
            .where(func.time(Sale.sold_at) >= time(9, 0))
            .where(func.time(Sale.sold_at) <= time(21, 0))
            .group_by(bucket_expression)
            .order_by(bucket_expression)
        )
        if db.info.get("read_store_id") is not None:
            trend_statement = trend_statement.where(SaleItem.store_id == db.info["read_store_id"])
        trend_result = await db.execute(trend_statement)
        for (
            bucket,
            original_revenue,
            revenue,
            discount_amount,
            sales_cost,
            gross_profit,
            quantity,
            sale_count,
        ) in trend_result.all():
            if isinstance(bucket, datetime):
                bucket_time = bucket
            elif isinstance(bucket, date):
                bucket_time = datetime.combine(bucket, time.min)
            else:
                bucket_time = datetime.fromisoformat(str(bucket))
            trend.append(
                (
                    bucket_time,
                    Decimal(original_revenue),
                    Decimal(revenue),
                    Decimal(discount_amount),
                    Decimal(sales_cost),
                    Decimal(gross_profit),
                    int(quantity),
                    int(sale_count),
                )
            )
    return (summary, departments, trend)


# endregion

__all__ = [
    "AnalyticsSummaryValues",
    "DepartmentReportValues",
    "RankingValues",
    "ReportValues",
    "get_departments_reports",
    "get_rankings",
    "get_reports",
    "get_report_analytics",
]
