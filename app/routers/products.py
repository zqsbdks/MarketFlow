"""商品查询 API 路由。"""

from fastapi import APIRouter, Body, Depends, Path
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies.auth import get_current_employee_id
from app.dependencies.db import get_db
from app.schemas.base import ResponseModel
from app.schemas.products_requests import (
    ProductsListRequest,
    ProductStatusUpdateRequest,
    UpdateProductRequest,
)
from app.schemas.products_responses import ItemResponse, ProductsListResponse
from app.services.products import (
    get_product_detail_service,
    get_products_list_service,
    update_product_service,
    update_product_status_service,
)

products_router = APIRouter(prefix="/products", tags=["products"])


# region 获取商品列表接口
@products_router.get(
    "/list",
    response_model=ResponseModel[ProductsListResponse],
    summary="获取商品列表",
    description="按照商品名称、部门、分类和销售状态筛选商品，并分页返回。",
)
async def get_products_list(
    request: ProductsListRequest = Depends(),
    current_employee_id: int = Depends(get_current_employee_id),
    db: AsyncSession = Depends(get_db),
) -> ResponseModel[ProductsListResponse]:
    """接收查询参数，并返回统一格式的商品列表响应。"""

    products = await get_products_list_service(
        page=request.page,
        page_size=request.page_size,
        keyword=request.keyword,
        department_id=request.department_id,
        category_id=request.category_id,
        status=request.status,
        current_employee_id=current_employee_id,
        db=db,
    )

    return ResponseModel[ProductsListResponse](
        message="商品列表获取成功",
        data=products,
    )


# endregion


# region 获取商品详情接口
@products_router.get(
    "/{product_id}",
    response_model=ResponseModel[ItemResponse],
    summary="获取商品详情",
    description="根据商品ID获取商品的详细信息。",
)
async def get_product_detail(
    product_id: int = Path(..., description="商品ID", ge=1),
    current_employee_id: int = Depends(get_current_employee_id),
    db: AsyncSession = Depends(get_db),
) -> ResponseModel[ItemResponse]:
    """接收商品 ID，并返回统一格式的商品详情响应。"""

    product = await get_product_detail_service(
        product_id=product_id,
        current_employee_id=current_employee_id,
        db=db,
    )

    return ResponseModel[ItemResponse](
        message="商品详情获取成功",
        data=product,
    )


# endregion


# region 修改商品状态接口
@products_router.put(
    "/{product_id}/status",
    response_model=ResponseModel[ItemResponse],
    summary="修改商品状态",
    description="店长可修改全部商品，正式员工只能修改自己所属部门的商品状态。",
)
async def update_product_status(
    # product_id 来自 URL 路径，例如 PUT /products/12/status 中的 12。
    product_id: int = Path(..., description="商品ID", ge=1),
    # request 是 JSON 请求体，只接收准备修改的新商品销售状态。
    request: ProductStatusUpdateRequest = Body(...),
    # current_employee_id 由登录令牌解析得到，用于判断角色和部门权限。
    current_employee_id: int = Depends(get_current_employee_id),
    # db 是当前请求使用的异步数据库会话。
    db: AsyncSession = Depends(get_db),
) -> ResponseModel[ItemResponse]:
    """接收商品 ID 和新状态，并返回修改后的完整商品详情。"""

    # Router 负责接收参数，账号、角色和部门权限交给 Service 检查。
    product = await update_product_status_service(
        product_id=product_id,
        request=request,
        current_employee_id=current_employee_id,
        db=db,
    )

    # 状态接口与商品详情、资料修改接口使用相同的响应模型。
    return ResponseModel[ItemResponse](
        message="商品状态修改成功",
        data=product,
    )


# endregion


# region 修改商品接口
@products_router.put(
    "/{product_id}",
    response_model=ResponseModel[ItemResponse],
    summary="修改商品",
    description="根据商品ID修改商品的详细信息。",
)
async def update_product(
    # product_id 来自 URL 路径，例如 PUT /products/12 中的 12。
    product_id: int = Path(..., description="商品ID", ge=1),
    # request 是前端提交的 JSON 请求体，只包含本次需要修改的商品字段。
    request: UpdateProductRequest = Body(...),
    # current_employee_id 由登录令牌解析得到，用于判断操作权限。
    current_employee_id: int = Depends(get_current_employee_id),
    # db 是当前请求使用的异步数据库会话。
    db: AsyncSession = Depends(get_db),
) -> ResponseModel[ItemResponse]:
    """接收商品 ID 和修改请求，并返回统一格式的商品详情响应。"""

    # Router 只负责接收参数；权限校验、字段校验和数据库更新交给 Service。
    product = await update_product_service(
        product_id=product_id,
        request=request,
        current_employee_id=current_employee_id,
        db=db,
    )

    # 使用项目统一响应结构包装修改后的商品详情。
    return ResponseModel[ItemResponse](
        message="商品修改成功",
        data=product,
    )


# endregion


__all__ = ["products_router"]
