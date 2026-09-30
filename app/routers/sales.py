"""销售记录 API 路由。"""

from fastapi import APIRouter, Depends, Path
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies.auth import get_current_employee_id
from app.dependencies.db import get_db
from app.schemas.base import ResponseModel
from app.schemas.sales_requests import CreateSaleRequest, SalesListRequest
from app.schemas.sales_responses import (
    SaleDetailResponse,
    SalePricePreviewResponse,
    SalesListResponse,
)
from app.services.sales import (
    create_sale_service,
    get_sales_detail_service,
    get_sales_list_service,
    preview_sale_price_service,
)

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


# region 预览销售价格
@sales_router.post(
    "/preview",
    response_model=ResponseModel[SalePricePreviewResponse],
    summary="预览销售价格",
    description="按照当前生效折扣计算商品原价、优惠金额和预计实付金额，不扣库存也不创建销售单。",
)
async def preview_sale_price(
    request: CreateSaleRequest,
    current_employee_id: int = Depends(get_current_employee_id),
    db: AsyncSession = Depends(get_db),
) -> ResponseModel[SalePricePreviewResponse]:
    """接收扫码商品和数量，返回当前时刻的折扣试算结果。"""

    preview = await preview_sale_price_service(
        request=request,
        current_employee_id=current_employee_id,
        db=db,
    )
    return ResponseModel[SalePricePreviewResponse](
        message="销售价格预览成功",
        data=preview,
    )


# endregion


# region 创建销售单
@sales_router.post(
    "",
    response_model=ResponseModel[SaleDetailResponse],
    summary="创建销售单",
    description="模拟收银台扫码结账，按最早到期批次扣减库存并生成销售小票。",
)
async def create_sale(
    request: CreateSaleRequest,
    current_employee_id: int = Depends(get_current_employee_id),
    db: AsyncSession = Depends(get_db),
) -> ResponseModel[SaleDetailResponse]:
    """接收商品及数量，返回合并同商品批次后的销售小票。"""

    sale = await create_sale_service(
        request=request,
        current_employee_id=current_employee_id,
        db=db,
    )
    return ResponseModel[SaleDetailResponse](message="销售单创建成功", data=sale)


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
