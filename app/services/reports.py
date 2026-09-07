"""营业报表业务逻辑。"""

from datetime import datetime, time, timedelta
from decimal import Decimal
from typing import Any, Literal

from fastapi import HTTPException
from fastapi import status as http_status
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.auth import get_employee_by_id
from app.crud.categories import get_category_by_id
from app.crud.employees import get_department_by_id
from app.crud.reports import (
    get_departments_reports,
    get_rankings,
    get_report_analytics,
    get_reports,
)
from app.models.enums import RankingGroupBy, RankingSortBy, RankingSortOrder, ReportMetric
from app.schemas.reports_responses import (
    DepartmentResponse,
    RankingItemResponse,
    RankingsResponse,
    ReportAnalyticsResponse,
    ReportResponse,
)

BUSINESS_OPENING_TIME = time(9, 0)
BUSINESS_CLOSING_TIME = time(21, 0)


# region 获取营业概览
async def overview_service(
    db: AsyncSession,
    employee_id: int,
    start_time: datetime | None,
    end_time: datetime | None,
    department_id: int | None,
) -> ReportResponse:
    """验证员工和查询条件，并返回营业概览。"""

    employee = await get_employee_by_id(employee_id=employee_id, db=db)
    if employee is None:
        raise HTTPException(
            status_code=http_status.HTTP_401_UNAUTHORIZED,
            detail="当前登录员工不存在",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not employee.is_active:
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail="账号已停用",
        )

    if employee.must_change_password:
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail="请先修改初始密码",
        )

    # 查询时间必须位于超市每天的营业时间之内。
    if start_time is not None:
        selected_start_time = start_time.time()
        if not BUSINESS_OPENING_TIME <= selected_start_time <= BUSINESS_CLOSING_TIME:
            raise HTTPException(
                status_code=http_status.HTTP_400_BAD_REQUEST,
                detail="开始时间必须在 09:00 至 21:00 之间",
            )

    if end_time is not None:
        selected_end_time = end_time.time()
        if not BUSINESS_OPENING_TIME <= selected_end_time <= BUSINESS_CLOSING_TIME:
            raise HTTPException(
                status_code=http_status.HTTP_400_BAD_REQUEST,
                detail="结束时间必须在 09:00 至 21:00 之间",
            )

    if start_time is not None and end_time is not None and start_time >= end_time:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail="开始时间必须早于结束时间",
        )

    # 传入部门ID时先确认部门真实存在；不传则统计整个店铺。
    if department_id is not None:
        department = await get_department_by_id(
            department_id=department_id,
            db=db,
        )
        if department is None:
            raise HTTPException(
                status_code=http_status.HTTP_404_NOT_FOUND,
                detail="部门不存在",
            )

    revenue, sales_cost, gross_profit, sales_quantity, sale_count = await get_reports(
        db=db,
        start_time=start_time,
        end_time=end_time,
        department_id=department_id,
    )

    return ReportResponse(
        revenue=revenue,
        sales_cost=sales_cost,
        gross_profit=gross_profit,
        sales_quantity=sales_quantity,
        sale_count=sale_count,
    )


# endregion


# region 获取部门营业对比
async def get_departments_service(
    db: AsyncSession,
    employee_id: int,
    start_time: datetime | None,
    end_time: datetime | None,
) -> list[DepartmentResponse]:
    """验证员工和查询时间，并返回所有部门的营业对比数据。"""

    employee = await get_employee_by_id(employee_id=employee_id, db=db)
    if employee is None:
        raise HTTPException(
            status_code=http_status.HTTP_401_UNAUTHORIZED,
            detail="当前登录员工不存在",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not employee.is_active:
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail="账号已停用",
        )

    if employee.must_change_password:
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail="请先修改初始密码",
        )

    if start_time is not None:
        selected_start_time = start_time.time()
        if not BUSINESS_OPENING_TIME <= selected_start_time <= BUSINESS_CLOSING_TIME:
            raise HTTPException(
                status_code=http_status.HTTP_400_BAD_REQUEST,
                detail="开始时间必须在 09:00 至 21:00 之间",
            )

    if end_time is not None:
        selected_end_time = end_time.time()
        if not BUSINESS_OPENING_TIME <= selected_end_time <= BUSINESS_CLOSING_TIME:
            raise HTTPException(
                status_code=http_status.HTTP_400_BAD_REQUEST,
                detail="结束时间必须在 09:00 至 21:00 之间",
            )

    if start_time is not None and end_time is not None and start_time >= end_time:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail="开始时间必须早于结束时间",
        )

    department_values = await get_departments_reports(
        db=db,
        start_time=start_time,
        end_time=end_time,
    )

    departments: list[DepartmentResponse] = []
    for department_id, department_name, revenue, gross_profit, sales_quantity in department_values:
        department = DepartmentResponse(
            department_id=department_id,
            department_name=department_name,
            revenue=revenue,
            gross_profit=gross_profit,
            sales_quantity=sales_quantity,
        )
        departments.append(department)

    return departments


# endregion


# region 获取销售排行
async def get_rankings_service(
    db: AsyncSession,
    employee_id: int,
    start_date: datetime | None,
    end_date: datetime | None,
    department_id: int | None,
    category_id: int | None,
    group_by: RankingGroupBy,
    sort_by: RankingSortBy,
    sort_order: RankingSortOrder,
    page: int,
    page_size: int,
) -> RankingsResponse:
    """验证员工和查询参数，并返回销售排行。"""

    employee = await get_employee_by_id(employee_id=employee_id, db=db)
    if employee is None:
        raise HTTPException(
            status_code=http_status.HTTP_401_UNAUTHORIZED,
            detail="当前登录员工不存在",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not employee.is_active:
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail="账号已停用",
        )

    if employee.must_change_password:
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail="请先修改初始密码",
        )

    if start_date is not None:
        selected_start_time = start_date.time()
        if not BUSINESS_OPENING_TIME <= selected_start_time <= BUSINESS_CLOSING_TIME:
            raise HTTPException(
                status_code=http_status.HTTP_400_BAD_REQUEST,
                detail="开始时间必须在 09:00 至 21:00 之间",
            )

    if end_date is not None:
        selected_end_time = end_date.time()
        if not BUSINESS_OPENING_TIME <= selected_end_time <= BUSINESS_CLOSING_TIME:
            raise HTTPException(
                status_code=http_status.HTTP_400_BAD_REQUEST,
                detail="结束时间必须在 09:00 至 21:00 之间",
            )

    if start_date is not None and end_date is not None and start_date >= end_date:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail="开始时间必须早于结束时间",
        )

    if department_id is not None:
        department = await get_department_by_id(
            department_id=department_id,
            db=db,
        )
        if department is None:
            raise HTTPException(
                status_code=http_status.HTTP_404_NOT_FOUND,
                detail="部门不存在",
            )

    if category_id is not None:
        category = await get_category_by_id(category_id=category_id, db=db)
        if category is None:
            raise HTTPException(
                status_code=http_status.HTTP_404_NOT_FOUND,
                detail="商品分类不存在",
            )
        if department_id is not None and category.department_id != department_id:
            raise HTTPException(
                status_code=http_status.HTTP_400_BAD_REQUEST,
                detail="商品分类不属于所选部门",
            )

    offset = (page - 1) * page_size
    ranking_values, total = await get_rankings(
        db=db,
        start_date=start_date,
        end_date=end_date,
        department_id=department_id,
        category_id=category_id,
        group_by=group_by,
        sort_by=sort_by,
        sort_order=sort_order,
        offset=offset,
        page_size=page_size,
    )

    items: list[RankingItemResponse] = []
    for index, (item_id, item_name, quantity, amount) in enumerate(
        ranking_values,
        start=1,
    ):
        item = RankingItemResponse(
            rank=offset + index,
            id=item_id,
            name=item_name,
            quantity=quantity,
            amount=amount,
        )
        items.append(item)

    total_pages = (total + page_size - 1) // page_size
    return RankingsResponse(
        items=items,
        page=page,
        page_size=page_size,
        total=total,
        total_pages=total_pages,
    )


# endregion


# region 获取营业分析
def _percentage(numerator: Decimal, denominator: Decimal) -> Decimal | None:
    """计算百分数，并将结果保留两位小数。

    Args:
        numerator: 分子，例如毛利润或本期与上期的营业额差值。
        denominator: 分母，例如营业额或上一期营业额。

    Returns:
        Decimal | None: 可计算时返回百分数；分母为0时返回None。
    """

    # 除数不能为0；此时不存在有效百分比，所以用None表示“无法计算”。
    if denominator == 0:
        return None
    # 先用“分子÷分母×100”得到百分数，再用quantize固定保留两位小数。
    return (numerator / denominator * Decimal(100)).quantize(Decimal("0.01"))


def _build_sales_trend(
    raw_values: list[tuple[datetime, Decimal, Decimal, Decimal, int, int]],
    start_time: datetime,
    end_time: datetime,
    interval: Literal["hour", "day", "month", "year"],
) -> list[dict[str, Any]]:
    """将数据库分组结果转换成前端需要的营业趋势列表。

    Args:
        raw_values: CRUD查询出的原始分组数据。每一项依次包含时间段开始值、
            营业额、销售成本、毛利润、销售商品数量和销售单数量。
        start_time: 用户选择的查询开始时间，用于裁剪第一个时间段。
        end_time: 用户选择的查询结束时间，用于裁剪最后一个时间段。
        interval: 时间分组粒度，支持按小时、日、月或年。

    Returns:
        list[dict[str, Any]]: 前端表格和图表可以直接使用的趋势数据列表。
    """

    # 创建空列表；下面每处理一个有销售数据的时间段，就向列表添加一个字典。
    result: list[dict[str, Any]] = []

    # 逐项拆开CRUD返回的数据：bucket_start是分组起点，后面五项是该组的汇总值。
    for bucket_start, revenue, cost, profit, quantity, sale_count in raw_values:
        # 按小时查询时，一个时间段为一小时，例如09:00到10:00。
        if interval == "hour":
            # 当前分组起点增加一小时，得到这个小时分组的结束时间。
            next_bucket = bucket_start + timedelta(hours=1)
        # 按日查询时，一个时间段代表当天营业时间，而不是完整的24小时。
        elif interval == "day":
            # 数据库按日期分组得到的是当天00:00，这里改成门店开门时间09:00。
            bucket_start = datetime.combine(bucket_start.date(), BUSINESS_OPENING_TIME)
            # 使用同一天日期和门店关门时间21:00，组成当天分组的结束时间。
            next_bucket = datetime.combine(bucket_start.date(), BUSINESS_CLOSING_TIME)
        # 按月查询时，一个时间段从本月第一天开始，到下月第一天结束。
        elif interval == "month":
            # 12月的下一个月属于下一年，不能直接把月份加到13。
            if bucket_start.month == 12:
                # 年份增加1并把月份设为1，得到下一年1月1日。
                next_bucket = bucket_start.replace(year=bucket_start.year + 1, month=1)
            else:
                # 1月至11月只需把月份增加1，日期仍然保持为每月1日。
                next_bucket = bucket_start.replace(month=bucket_start.month + 1)
        # 前面三种情况都不满足时，interval就是year，表示按年查询。
        else:
            # 年份增加1，得到下一年度的开始时间，也就是本年度的结束边界。
            next_bucket = bucket_start.replace(year=bucket_start.year + 1)

        # 把当前时间段的起止时间和各项汇总数据组装成一个前端响应字典。
        result.append(
            {
                # 第一个分组可能早于用户选择的开始时间，因此取两个时间中较晚的一个。
                "start_time": max(bucket_start, start_time),
                # 最后一个分组可能超过用户选择的结束时间，因此取两个时间中较早的一个。
                "end_time": min(next_bucket, end_time),
                # 当前时间段内所有销售明细的销售小计之和，即营业额。
                "revenue": revenue,
                # 当前时间段内所有销售明细的成本小计之和，即销售成本。
                "sales_cost": cost,
                # 当前时间段的毛利润，等于营业额减去销售成本。
                "gross_profit": profit,
                # 当前时间段卖出的商品总件数。
                "sales_quantity": quantity,
                # 当前时间段去重后的销售单数量。
                "sale_count": sale_count,
                # 当前时间段毛利率＝毛利润÷营业额×100；营业额为0时结果为None。
                "gross_profit_margin": _percentage(profit, revenue),
            }
        )

    # 循环结束后，把已经按时间顺序组装好的趋势列表返回给调用方。
    return result


async def get_report_analytics_service(
    db: AsyncSession,
    employee_id: int,
    start_time: datetime,
    end_time: datetime,
    department_id: int | None,
    interval: Literal["hour", "day", "month", "year"],
    metrics: list[ReportMetric],
) -> ReportAnalyticsResponse:
    """验证查询条件，只计算并返回前端勾选的营业指标。

    Args:
        db: 当前请求使用的异步数据库会话。
        employee_id: 当前登录员工ID，用于确认账号存在且有权查看报表。
        start_time: 本期统计开始时间，查询时包含该时刻。
        end_time: 本期统计结束时间，查询时不包含该时刻。
        department_id: 要统计的部门ID；为None时统计全店。
        interval: 趋势数据的分组粒度，支持hour、day、month、year。
        metrics: 前端勾选的指标枚举列表，决定执行哪些查询和返回哪些字段。

    Returns:
        ReportAnalyticsResponse: 仅包含用户勾选字段的经营分析响应。
    """

    # 先按令牌中的员工ID重新读取账号，避免已删除或已停用的账号继续查看数据。
    employee = await get_employee_by_id(employee_id=employee_id, db=db)
    if employee is None:
        raise HTTPException(
            status_code=http_status.HTTP_401_UNAUTHORIZED,
            detail="当前登录员工不存在",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not employee.is_active:
        raise HTTPException(status_code=http_status.HTTP_403_FORBIDDEN, detail="账号已停用")
    if employee.must_change_password:
        raise HTTPException(status_code=http_status.HTTP_403_FORBIDDEN, detail="请先修改初始密码")

    if not BUSINESS_OPENING_TIME <= start_time.time() <= BUSINESS_CLOSING_TIME:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail="开始时间必须在 09:00 至 21:00 之间",
        )
    if not BUSINESS_OPENING_TIME <= end_time.time() <= BUSINESS_CLOSING_TIME:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail="结束时间必须在 09:00 至 21:00 之间",
        )
    if start_time >= end_time:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail="开始时间必须早于结束时间",
        )

    if department_id is not None:
        department = await get_department_by_id(department_id=department_id, db=db)
        if department is None:
            raise HTTPException(
                status_code=http_status.HTTP_404_NOT_FOUND,
                detail="部门不存在",
            )

    # 转成集合后，判断某个指标是否被选择更直观，也会自动去除重复指标。
    requested = set(metrics)
    summary_metrics = {
        ReportMetric.REVENUE,
        ReportMetric.SALES_COST,
        ReportMetric.GROSS_PROFIT,
        ReportMetric.SALES_QUANTITY,
        ReportMetric.SALE_COUNT,
        ReportMetric.AVERAGE_SALE_AMOUNT,
        ReportMetric.AVERAGE_SALE_QUANTITY,
        ReportMetric.GROSS_PROFIT_MARGIN,
        ReportMetric.REVENUE_GROWTH_RATE,
        ReportMetric.GROSS_PROFIT_GROWTH_RATE,
    }
    # 三个布尔值告诉CRUD究竟需要执行哪类SQL，避免勾选一项却查询全部数据。
    needs_summary = bool(requested & summary_metrics)  # 是否查询营业额、成本、数量等汇总值。
    needs_departments = ReportMetric.DEPARTMENT_REVENUE_SHARE in requested  # 是否查部门占比。
    needs_trend = ReportMetric.SALES_TREND in requested  # 是否按时间分组查询趋势。

    current, department_values, trend_values = await get_report_analytics(
        db=db,  # 当前数据库会话。
        start_time=start_time,  # 本期开始时间。
        end_time=end_time,  # 本期结束时间。
        department_id=department_id,  # None查全店，否则只汇总指定部门。
        interval=interval,  # 趋势的时间分组粒度。
        include_summary=needs_summary,  # True时执行汇总SQL。
        include_departments=needs_departments,  # True时执行部门占比SQL。
        include_trend=needs_trend,  # True时执行营业趋势SQL。
    )

    response_values: dict[str, Any] = {}
    if current is not None:
        # CRUD按固定顺序返回：营业额、成本、毛利润、商品数量、销售单数量。
        revenue, cost, gross_profit, quantity, sale_count = current
        if ReportMetric.REVENUE in requested:
            response_values[ReportMetric.REVENUE.value] = revenue
        if ReportMetric.SALES_COST in requested:
            response_values[ReportMetric.SALES_COST.value] = cost
        if ReportMetric.GROSS_PROFIT in requested:
            response_values[ReportMetric.GROSS_PROFIT.value] = gross_profit
        if ReportMetric.SALES_QUANTITY in requested:
            response_values[ReportMetric.SALES_QUANTITY.value] = quantity
        if ReportMetric.SALE_COUNT in requested:
            response_values[ReportMetric.SALE_COUNT.value] = sale_count
        if ReportMetric.AVERAGE_SALE_AMOUNT in requested:
            response_values[ReportMetric.AVERAGE_SALE_AMOUNT.value] = (
                (revenue / sale_count).quantize(Decimal("0.01")) if sale_count else None
            )
        if ReportMetric.AVERAGE_SALE_QUANTITY in requested:
            response_values[ReportMetric.AVERAGE_SALE_QUANTITY.value] = (
                (Decimal(quantity) / sale_count).quantize(Decimal("0.01")) if sale_count else None
            )
        if ReportMetric.GROSS_PROFIT_MARGIN in requested:
            response_values[ReportMetric.GROSS_PROFIT_MARGIN.value] = _percentage(
                gross_profit, revenue
            )

        needs_growth = bool(
            requested & {ReportMetric.REVENUE_GROWTH_RATE, ReportMetric.GROSS_PROFIT_GROWTH_RATE}
        )
        if needs_growth:
            # 对比紧邻本期之前、营业天数相同的日期范围。
            period_days = (end_time.date() - start_time.date()).days + 1
            previous_start = start_time - timedelta(days=period_days)
            previous_end = end_time - timedelta(days=period_days)
            previous, _, _ = await get_report_analytics(
                db=db,
                start_time=previous_start,
                end_time=previous_end,
                department_id=department_id,
                interval=interval,
                include_summary=True,
                include_departments=False,
                include_trend=False,
            )
            if previous is not None:
                previous_revenue, _previous_cost, previous_profit, _quantity, _sale_count = previous
                if ReportMetric.REVENUE_GROWTH_RATE in requested:
                    response_values[ReportMetric.REVENUE_GROWTH_RATE.value] = _percentage(
                        revenue - previous_revenue, previous_revenue
                    )
                if ReportMetric.GROSS_PROFIT_GROWTH_RATE in requested:
                    response_values[ReportMetric.GROSS_PROFIT_GROWTH_RATE.value] = (
                        _percentage(gross_profit - previous_profit, previous_profit)
                        if previous_profit > 0
                        else None
                    )

    if needs_departments:
        store_revenue = sum((row[2] for row in department_values), Decimal(0))
        shares: list[dict[str, Any]] = []
        for item_id, name, revenue in department_values:
            if department_id is not None and item_id != department_id:
                continue
            shares.append(
                {
                    "department_id": item_id,
                    "department_name": name,
                    "revenue_share": _percentage(revenue, store_revenue),
                }
            )
        response_values[ReportMetric.DEPARTMENT_REVENUE_SHARE.value] = shares

    if needs_trend:
        response_values[ReportMetric.SALES_TREND.value] = _build_sales_trend(
            trend_values, start_time, end_time, interval
        )

    # 只把选中的字段传给模型；未选字段保持“未设置”，路由会将其从JSON中排除。
    return ReportAnalyticsResponse(**response_values)


# endregion

__all__ = [
    "BUSINESS_CLOSING_TIME",
    "BUSINESS_OPENING_TIME",
    "get_departments_service",
    "get_rankings_service",
    "get_report_analytics_service",
    "overview_service",
]
