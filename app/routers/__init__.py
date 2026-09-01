"""顶层 API 路由聚合模块。

每个业务模块应拥有自己的 ``APIRouter``，再通过 ``api_router.include_router``
挂载到这里。应用工厂只需要包含该聚合路由即可。
"""

from fastapi import APIRouter

# 该对象最终在 app.main 中统一添加 /api/v1 前缀。
api_router = APIRouter()

__all__ = ["api_router"]
