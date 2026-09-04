"""营业报表 API 路由。"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies.auth import get_current_employee_id
from app.dependencies.db import get_db
from app.schemas.base import ResponseModel
from app.schemas.reports_requests import DepartmentRequest, RankingsRequest, ReportRequest
from app.schemas.reports_responses import (
    DepartmentResponse,
    RankingsResponse,
    ReportResponse,
)
from app.services.reports import (
    get_departments_service,
    get_rankings_service,
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

__all__ = ["reports_router"]
