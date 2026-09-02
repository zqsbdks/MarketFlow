"""商品查询 API 路由。"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies.auth import get_current_employee_id
from app.dependencies.db import get_db
from app.schemas.base import ResponseModel
from app.schemas.products_requests import ProductsListRequest
from app.schemas.products_responses import ProductsListResponse
from app.services.products import get_products_list_service

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


__all__ = ["products_router"]
