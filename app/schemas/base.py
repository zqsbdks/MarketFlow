"""通用响应模型模块。

所有接口都可以使用这里定义的统一响应结构，确保前端在接收成功和失败响应时，
都能使用一致的字段格式。
"""

from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict

T = TypeVar("T")


class ResponseModel(BaseModel, Generic[T]):
    """统一封装接口响应中的 code、message 和 data 字段。

    Args:
        code (int): HTTP 或业务状态码。
        message (str): 响应提示信息。
        data (T): 响应的数据内容；没有数据时为 ``None``。
    """

    code: int = 200  # HTTP/业务状态码，默认表示成功。
    message: str = "success"  # 面向调用方的简短提示。
    data: T | None = None  # 泛型载荷，允许每个接口声明自己的数据类型。

    # from_attributes=True 支持直接从 SQLAlchemy 等属性对象构造响应模型。
    model_config = ConfigDict(from_attributes=True)


__all__ = ["ResponseModel"]
