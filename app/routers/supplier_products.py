"""供应商商品目录 API 路由。"""

from fastapi import APIRouter, Depends, Path  # noqa: F401
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: F401

from app.dependencies.auth import get_current_employee_id  # noqa: F401
from app.dependencies.db import get_db  # noqa: F401
from app.schemas.base import ResponseModel  # noqa: F401

# 最终接口地址统一以 /api/v1/supplier-products 开头。
supplier_products_router = APIRouter(
    prefix="/supplier-products",
    tags=["supplier-products"],
)


# 后续接口按照以下顺序编写：
# 1. 获取供应商商品列表
# 2. 获取供应商商品详情
# 3. 创建供应商商品
# 4. 修改供应商商品状态
# 5. 修改供应商商品详情

__all__ = ["supplier_products_router"]
