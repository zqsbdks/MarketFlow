"""供应商商品目录 API 路由。"""

from fastapi import APIRouter, Depends, Path
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies.auth import get_current_employee_id
from app.dependencies.db import get_db
from app.schemas.base import ResponseModel
from app.schemas.supplier_products_requests import (
    SupplierProductCreateRequest,
    SupplierProductsListRequest,
    SupplierProductStatusUpdateRequest,
    SupplierProductUpdateRequest,
)
from app.schemas.supplier_products_responses import (
    SupplierProductItemResponse,
    SupplierProductListResponse,
)
from app.services.supplier_products import (
    create_supplier_product_service,
    get_supplier_product_detail_service,
    get_supplier_products_list_service,
    update_supplier_product_service,
    update_supplier_product_status_service,
)

supplier_products_router = APIRouter(
    prefix="/supplier-products",
    tags=["supplier-products"],
)


# region 获取供应商商品列表
@supplier_products_router.get(
    "/list",
    response_model=ResponseModel[SupplierProductListResponse],
    summary="获取供应商商品列表",
    description="分页获取供应商商品目录，并可按供应商、商品名称和供应状态筛选。",
)
async def get_supplier_products_list(
    request: SupplierProductsListRequest = Depends(),
    current_employee_id: int = Depends(get_current_employee_id),
    db: AsyncSession = Depends(get_db),
) -> ResponseModel[SupplierProductListResponse]:
    """接收查询参数，并使用统一响应格式返回供应商商品列表。"""

    supplier_products = await get_supplier_products_list_service(
        page=request.page,
        page_size=request.page_size,
        supplier_id=request.supplier_id,
        keyword=request.keyword,
        is_active=request.is_active,
        current_employee_id=current_employee_id,
        db=db,
    )
    return ResponseModel[SupplierProductListResponse](
        message="获取供应商商品列表成功",
        data=supplier_products,
    )


# endregion


# region 获取供应商商品详情
@supplier_products_router.get(
    "/{supplier_product_id}",
    response_model=ResponseModel[SupplierProductItemResponse],
    summary="获取供应商商品详情",
    description="根据供应商商品目录ID获取详细资料。",
)
async def get_supplier_product_detail(
    supplier_product_id: int = Path(..., description="供应商商品目录ID", ge=1),
    current_employee_id: int = Depends(get_current_employee_id),
    db: AsyncSession = Depends(get_db),
) -> ResponseModel[SupplierProductItemResponse]:
    """接收目录ID，并返回对应的供应商商品详情。"""

    supplier_product = await get_supplier_product_detail_service(
        supplier_product_id=supplier_product_id,
        current_employee_id=current_employee_id,
        db=db,
    )
    return ResponseModel[SupplierProductItemResponse](
        message="获取供应商商品详情成功",
        data=supplier_product,
    )


# endregion


# region 创建供应商商品
@supplier_products_router.post(
    "",
    response_model=ResponseModel[SupplierProductItemResponse],
    summary="创建供应商商品",
    description="店长向指定供应商的商品目录中添加商品。",
)
async def create_supplier_product(
    request: SupplierProductCreateRequest,
    current_employee_id: int = Depends(get_current_employee_id),
    db: AsyncSession = Depends(get_db),
) -> ResponseModel[SupplierProductItemResponse]:
    """接收商品资料，并返回创建后的供应商商品。"""

    supplier_product = await create_supplier_product_service(
        request=request,
        current_employee_id=current_employee_id,
        db=db,
    )
    return ResponseModel[SupplierProductItemResponse](
        message="创建供应商商品成功",
        data=supplier_product,
    )


# endregion


# region 修改供应商商品状态
@supplier_products_router.put(
    "/{supplier_product_id}/status",
    response_model=ResponseModel[SupplierProductItemResponse],
    summary="修改供应商商品状态",
    description="店长启用或停用指定的供应商商品。",
)
async def update_supplier_product_status(
    request: SupplierProductStatusUpdateRequest,
    supplier_product_id: int = Path(..., description="供应商商品目录ID", ge=1),
    current_employee_id: int = Depends(get_current_employee_id),
    db: AsyncSession = Depends(get_db),
) -> ResponseModel[SupplierProductItemResponse]:
    """接收目录ID和新状态，并返回修改后的供应商商品。"""

    supplier_product = await update_supplier_product_status_service(
        supplier_product_id=supplier_product_id,
        is_active=request.is_active,
        current_employee_id=current_employee_id,
        db=db,
    )
    return ResponseModel[SupplierProductItemResponse](
        message="修改供应商商品状态成功",
        data=supplier_product,
    )


# endregion


# region 修改供应商商品详情
@supplier_products_router.put(
    "/{supplier_product_id}",
    response_model=ResponseModel[SupplierProductItemResponse],
    summary="修改供应商商品详情",
    description="店长修改指定供应商商品的名称、进货价或默认保质期。",
)
async def update_supplier_product_details(
    request: SupplierProductUpdateRequest,
    supplier_product_id: int = Path(..., description="供应商商品目录ID", ge=1),
    current_employee_id: int = Depends(get_current_employee_id),
    db: AsyncSession = Depends(get_db),
) -> ResponseModel[SupplierProductItemResponse]:
    """接收目录ID和实际修改字段，并返回修改后的供应商商品。"""

    supplier_product = await update_supplier_product_service(
        supplier_product_id=supplier_product_id,
        request=request,
        current_employee_id=current_employee_id,
        db=db,
    )
    return ResponseModel[SupplierProductItemResponse](
        message="修改供应商商品详情成功",
        data=supplier_product,
    )


# endregion

__all__ = ["supplier_products_router"]
