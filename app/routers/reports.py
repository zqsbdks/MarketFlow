"""营业报表 API 路由。"""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies.auth import get_current_employee_id
from app.dependencies.db import get_db
from app.schemas.base import ResponseModel
from app.schemas.reports_requests import (
    DepartmentRequest,
    RankingsRequest,
    ReportAnalyticsRequest,
    ReportRequest,
)
from app.schemas.reports_responses import (
    DepartmentResponse,
    RankingsResponse,
    ReportAnalyticsResponse,
    ReportResponse,
)
from app.services.reports import (
    get_departments_service,
    get_rankings_service,
    get_report_analytics_service,
    overview_service,
)

reports_router = APIRouter(
    prefix="/reports",
    tags=["reports"],
)


# region 获取营业概览接口
@reports_router.get(
    "/overview",
    response_model=ResponseModel[ReportResponse],
    summary="获取营业概览",
    description="获取整个店铺或指定部门在所选时间范围内的营业汇总数据。",
)
async def overview(
    request: ReportRequest = Depends(),
    employee_id: int = Depends(get_current_employee_id),
    db: AsyncSession = Depends(get_db),
) -> ResponseModel[ReportResponse]:
    """接收报表查询参数，并返回统一格式的营业概览。"""

    report = await overview_service(
        db=db,
        employee_id=employee_id,
        start_time=request.start_time,
        end_time=request.end_time,
        department_id=request.department_id,
    )

    return ResponseModel[ReportResponse](
        message="获取营业概览数据成功",
        data=report,
    )


# endregion


# region 获取销售排行接口
@reports_router.get(
    "/rankings",
    response_model=ResponseModel[RankingsResponse],
    summary="获取销售排行",
    description="按商品或商品分类汇总销售数量和销售金额，并支持排序与分页。",
)
async def get_sales_rankings(
    request: RankingsRequest = Depends(),
    employee_id: int = Depends(get_current_employee_id),
    db: AsyncSession = Depends(get_db),
) -> ResponseModel[RankingsResponse]:
    """接收排行查询参数，并返回统一格式的销售排行。"""

    rankings = await get_rankings_service(
        db=db,
        employee_id=employee_id,
        start_date=request.start_date,
        end_date=request.end_date,
        department_id=request.department_id,
        category_id=request.category_id,
        group_by=request.group_by,
        sort_by=request.sort_by,
        sort_order=request.sort_order,
        page=request.page,
        page_size=request.page_size,
    )

    return ResponseModel[RankingsResponse](
        message="获取销售排行成功",
        data=rankings,
    )


# endregion


# region 获取部门销售对比接口


@reports_router.get(
    "/departments",
    response_model=ResponseModel[list[DepartmentResponse]],
    summary="获取四个部门销售对比",
    description="一次获取所有部门在所选时间范围内的营业对比数据。",
)
async def get_departments(
    db: AsyncSession = Depends(get_db),
    employee_id: int = Depends(get_current_employee_id),
    request: DepartmentRequest = Depends(),
) -> ResponseModel[list[DepartmentResponse]]:
    """接收时间查询参数，并返回统一格式的部门营业对比。"""

    departments = await get_departments_service(
        db=db,
        employee_id=employee_id,
        start_time=request.start_time,
        end_time=request.end_time,
    )

    return ResponseModel[list[DepartmentResponse]](
        message="获取部门销售对比数据成功",
        data=departments,
    )


# endregion


@reports_router.get(
    "/analytics",
    response_model=ResponseModel[ReportAnalyticsResponse],
    # 未勾选的响应字段没有被赋值，因此不会出现在最终JSON中。
    response_model_exclude_unset=True,
    summary="获取营业分析",
    description="根据metrics参数，只计算并返回前端勾选的营业指标。",
)
async def get_report_analytics(
    request: Annotated[ReportAnalyticsRequest, Query()],
    employee_id: int = Depends(get_current_employee_id),
    db: AsyncSession = Depends(get_db),
) -> ResponseModel[ReportAnalyticsResponse]:
    """接收多个指标名称，并返回统一格式的按需营业分析。

    Args:
        request: 前端传入的查询条件，包含起止时间、部门ID、统计粒度和指标列表。
        employee_id: 当前登录员工的ID，由访问令牌自动解析，不需要前端传入。
        db: 当前请求使用的异步数据库会话，由FastAPI自动创建和关闭。

    Returns:
        ResponseModel[ReportAnalyticsResponse]: 统一响应外层，以及本次勾选的分析结果。
    """

    # Router只负责接收参数；权限验证、指标计算和响应组装都交给Service处理。
    analytics = await get_report_analytics_service(
        db=db,  # 当前请求的数据库会话。
        employee_id=employee_id,  # 当前登录员工ID，用来验证查看报表的权限。
        start_time=request.start_time,  # 用户选择的统计开始时间，包含该时刻。
        end_time=request.end_time,  # 用户选择的统计结束时间，不包含该时刻。
        department_id=request.department_id,  # 部门ID；None表示查询全店。
        interval=request.interval,  # 趋势粒度：小时、日、月或年。
        metrics=request.metrics,  # 用户勾选的指标；未勾选指标不会计算和返回。
    )

    return ResponseModel[ReportAnalyticsResponse](
        # 本接口会排除未勾选指标；显式赋值可避免默认code也被一并排除。
        code=200,
        message="获取营业分析成功",
        data=analytics,
    )


__all__ = ["reports_router"]
