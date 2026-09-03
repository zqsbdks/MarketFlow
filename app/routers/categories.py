"""商品分类查询 API 路由。"""

from fastapi import APIRouter

categories_router = APIRouter(
    prefix="/categories",
    tags=["categories"],
)


__all__ = ["categories_router"]
