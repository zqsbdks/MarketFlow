"""Pydantic 请求与响应模型包。

业务 Schema 可按领域拆分为独立文件；跨模块常用的类型可以在这里统一重导出。
"""

from app.schemas.base import ResponseModel

__all__ = ["ResponseModel"]
