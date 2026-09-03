"""营业报表 API 路由。"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies.auth import get_current_employee_id
from app.dependencies.db import get_db
from app.schemas.base import ResponseModel
from app.schemas.reports_requests import ReportRequest
from app.schemas.reports_responses import ReportResponse
from app.services.reports import overview_service

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


__all__ = ["reports_router"]
