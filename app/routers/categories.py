"""商品分类查询 API 路由。"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies.auth import get_current_employee_id
from app.dependencies.db import get_db
from app.schemas.base import ResponseModel
from app.schemas.categories_requests import CategoryListRequest
from app.schemas.categories_responses import CategoriesItemResponse
from app.services.categories import get_categories_list_service

categories_router = APIRouter(
    prefix="/categories",
    tags=["categories"],
)


# region 获取商品分类列表接口
@categories_router.get(
    "/list",
    response_model=ResponseModel[list[CategoriesItemResponse]],
    summary="获取商品分类列表",
    description="返回商品分类列表，并支持按照部门ID筛选。",
)
async def get_list_categories(
    request: CategoryListRequest = Depends(),
    current_employee_id: int = Depends(get_current_employee_id),
    db: AsyncSession = Depends(get_db),
) -> ResponseModel[list[CategoriesItemResponse]]:
    """获取商品分类列表，并使用项目统一响应格式返回。"""

    categories = await get_categories_list_service(
        department_id=request.department_id,
        current_employee_id=current_employee_id,
        db=db,
    )

    return ResponseModel[list[CategoriesItemResponse]](
        message="获取商品分类列表成功",
        data=categories,
    )


# endregion


__all__ = ["categories_router"]
