"""销售记录 API 路由。"""

from fastapi import APIRouter, Depends, Path
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies.auth import get_current_employee_id
from app.dependencies.db import get_db
from app.schemas.base import ResponseModel
from app.schemas.sales_requests import SalesListRequest
from app.schemas.sales_responses import SaleDetailResponse, SalesListResponse
from app.services.sales import get_sales_detail_service, get_sales_list_service

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


# region 获取销售单详情接口
@sales_router.get(
    "/{sale_no}",
    response_model=ResponseModel[SaleDetailResponse],
    summary="获取销售单详情",
    description="根据销售单号获取销售单及其商品明细。",
)
async def get_sale_detail(
    sale_no: str = Path(
        ...,
        description="销售单号",
        min_length=1,
        max_length=30,
    ),
    current_employee_id: int = Depends(get_current_employee_id),
    db: AsyncSession = Depends(get_db),
) -> ResponseModel[SaleDetailResponse]:
    """根据销售单号返回一张销售单的详细信息。"""

    sale = await get_sales_detail_service(
        sale_no=sale_no,
        current_employee_id=current_employee_id,
        db=db,
    )

    return ResponseModel[SaleDetailResponse](
        message="获取销售单详情成功",
        data=sale,
    )


# endregion


__all__ = ["sales_router"]
