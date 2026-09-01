"""全局中间件配置模块。

本模块负责为 FastAPI 应用添加跨域中间件，使前端页面能够正常调用后端接口。
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings


def register_middlewares(app: FastAPI) -> None:
    """为 FastAPI 应用添加全局跨域中间件配置。

    Args:
        app (FastAPI): 需要注册中间件的应用实例。
    """

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,  # 允许访问 API 的前端 Origin 列表。
        # 浏览器不允许通配来源与凭据同时使用，因此 "*" 时自动禁用凭据。
        allow_credentials="*" not in settings.cors_origins,
        allow_methods=["*"],  # 允许的 HTTP 方法 (GET, POST, PUT, DELETE 等)。
        allow_headers=["*"],  # 允许的 HTTP 请求头。
    )


__all__ = ["register_middlewares"]
