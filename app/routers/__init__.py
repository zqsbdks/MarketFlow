"""顶层 API 路由聚合模块。

每个业务模块应拥有自己的 ``APIRouter``，再通过 ``api_router.include_router``
挂载到这里。应用工厂只需要包含该聚合路由即可。
"""

from fastapi import APIRouter

from app.routers.auth import auth_router
from app.routers.categories import categories_router
from app.routers.departments import departments_router
from app.routers.employees import employees_router
from app.routers.products import products_router
from app.routers.sales import sales_router

# 该对象最终在 app.main 中统一添加 /api/v1 前缀。
api_router = APIRouter()

api_router.include_router(auth_router)
api_router.include_router(departments_router)
api_router.include_router(categories_router)
api_router.include_router(employees_router)
api_router.include_router(products_router)
api_router.include_router(sales_router)

__all__ = [
    "api_router",
    "auth_router",
    "categories_router",
    "departments_router",
    "employees_router",
    "products_router",
    "sales_router",
]
