"""销售记录 API 路由。"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies.auth import get_current_employee_id
from app.dependencies.db import get_db
from app.schemas.base import ResponseModel
from app.schemas.sales_requests import SalesListRequest
from app.schemas.sales_responses import SalesListResponse
from app.services.sales import get_sales_list_service

sales_router = APIRouter(tags=["sales"], prefix="/sales")


# region 获取销售单列表接口
@sales_router.get(
    "/list",
    response_model=ResponseModel[SalesListResponse],
    summary="获取销售单列表",
    description="按照具体时间或销售单号筛选，并分页返回一张张收银记录。",
)
async def get_sales(
    request: SalesListRequest = Depends(),
    current_employee_id: int = Depends(get_current_employee_id),
    db: AsyncSession = Depends(get_db),
) -> ResponseModel[SalesListResponse]:
    """接收销售单查询参数，并返回统一格式的销售单列表。"""

    sales = await get_sales_list_service(
        page=request.page,
        page_size=request.page_size,
        start_time=request.start_time,
        end_time=request.end_time,
        sale_no=request.sale_no,
        current_employee_id=current_employee_id,
        db=db,
    )

    return ResponseModel[SalesListResponse](
        message="获取销售单列表成功",
        data=sales,
    )


# endregion


__all__ = ["sales_router"]
