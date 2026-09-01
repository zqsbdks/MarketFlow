"""FastAPI 应用统一响应模型与全局异常处理模块。

该模块定义了标准的 API 响应数据结构，并集中管理各类异常的捕获与响应格式，
确保前端接收到统一规范的 JSON 错误信息。
"""

import logging
import traceback
from collections.abc import Mapping
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.config import settings
from app.schemas import ResponseModel

logger = logging.getLogger(__name__)  # 获取当前模块的日志记录器。


# ----------------------------------------------------------------------
# 1. 核心异常响应生成器 (单点控制 JSON 结构与序列化)
# ----------------------------------------------------------------------
def create_exception_response(
    status_code: int,
    message: str,
    error_data: dict[str, Any] | None = None,
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    """统一异常响应生成器。

    该函数会将错误信息包装为统一的 code/message/data 格式，并返回 JSON 响应，
    方便前端统一解析不同类型的异常。

    Args:
        status_code (int): HTTP 状态码。
        message (str): 错误提示信息。
        error_data (dict[str, Any] | None, optional): 具体错误数据，
            仅在调试模式下提供，默认为 None。
        headers: 需要保留的响应头，例如 Bearer 认证挑战头。

    Returns:
        JSONResponse: 包含统一格式错误信息的 JSON 响应。
    """

    # 实例化统一响应模型，将错误信息包装在标准结构中。
    response_obj = ResponseModel[dict[str, Any] | None](
        code=status_code,
        message=message,
        data=error_data,
    )

    return JSONResponse(
        status_code=status_code,
        # mode="json" 确保 datetime、Decimal、UUID 等复杂类型能安全序列化为 JSON 字符串。
        content=response_obj.model_dump(mode="json"),
        headers=headers,
    )


# ----------------------------------------------------------------------
# 2. 各种具体异常处理器定义
# ----------------------------------------------------------------------


async def http_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """处理路由中主动抛出的 HTTPException，例如 404 或 401。

    Args:
        request (Request): FastAPI 请求对象。
        exc (HTTPException): 捕获到的 HTTP 异常实例。

    Returns:
        JSONResponse: 统一格式的错误 JSON 响应。
    """

    assert isinstance(exc, StarletteHTTPException)
    return create_exception_response(
        status_code=exc.status_code,
        message=str(exc.detail),
        error_data=None,
        headers=exc.headers,
    )


async def validation_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """处理前端传入参数校验失败的异常，例如 422。

    Args:
        request (Request): FastAPI 请求对象。
        exc (RequestValidationError): 捕获到的请求参数校验异常实例。

    Returns:
        JSONResponse: 统一格式的错误 JSON 响应。
    """

    assert isinstance(exc, RequestValidationError)
    errors = exc.errors()  # 获取 Pydantic 的校验错误详情列表。
    # 提取第一条错误信息作为主要提示，若无则使用默认提示。
    first_error_msg = errors[0].get("msg") if errors else "请求参数校验失败"

    error_data = None
    if settings.debug:
        # 在调试模式下，返回详细的错误类型、校验详情和请求路径以便排查。
        error_data = {
            "error_type": exc.__class__.__name__,
            "details": errors,
            "path": request.url.path,
        }

    return create_exception_response(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        message=f"参数错误: {first_error_msg}",
        error_data=error_data,
    )


async def integrity_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """处理数据库完整性约束错误，例如唯一索引冲突或外键约束报错。

    Args:
        request (Request): FastAPI 请求对象。
        exc (IntegrityError): 捕获到的数据库完整性异常实例。

    Returns:
        JSONResponse: 统一格式的错误 JSON 响应。
    """

    assert isinstance(exc, IntegrityError)
    error_msg = str(exc.orig)  # 获取数据库底层返回的原始错误信息。
    detail = "数据约束冲突，请检查输入"

    # 识别常见的数据库报错信息，转换为对用户友好的提示。
    if "username_UNIQUE" in error_msg or "Duplicate entry" in error_msg:
        detail = "记录已存在（唯一字段冲突）"
    elif "FOREIGN KEY" in error_msg:
        detail = "关联外键数据不存在"

    error_data = None
    if settings.debug:
        # 调试模式下暴露原始数据库报错以便调试。
        error_data = {
            "error_type": exc.__class__.__name__,
            "error_detail": error_msg,
            "path": request.url.path,
        }

    return create_exception_response(
        status_code=status.HTTP_400_BAD_REQUEST,
        message=detail,
        error_data=error_data,
    )


async def sqlalchemy_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """处理通用的 SQLAlchemy 数据库查询异常。

    Args:
        request (Request): FastAPI 请求对象。
        exc (SQLAlchemyError): 捕获到的 SQLAlchemy 异常实例。

    Returns:
        JSONResponse: 统一格式的错误 JSON 响应。
    """

    assert isinstance(exc, SQLAlchemyError)
    logger.error(f"数据库操作异常: {exc}", exc_info=True)  # 记录完整的错误堆栈日志。

    error_data = None
    if settings.debug:
        # 调试模式下返回异常类型、详情、堆栈跟踪和请求路径。
        error_data = {
            "error_type": exc.__class__.__name__,
            "error_detail": str(exc),
            "traceback": traceback.format_exc(),
            "path": request.url.path,
        }

    return create_exception_response(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        message="数据库操作失败，请稍后重试",
        error_data=error_data,
    )


async def general_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """未捕获异常兜底处理器，提供服务器 500 的统一兜底响应。

    Args:
        request (Request): FastAPI 请求对象。
        exc (Exception): 捕获到的未知异常实例。

    Returns:
        JSONResponse: 统一格式的错误 JSON 响应。
    """

    logger.error(f"服务器未知错误: {exc}", exc_info=True)  # 记录完整的错误堆栈日志。

    error_data = None
    if settings.debug:
        # 调试模式下返回异常类型、详情、堆栈跟踪和请求路径。
        error_data = {
            "error_type": exc.__class__.__name__,
            "error_detail": str(exc),
            "traceback": traceback.format_exc(),
            "path": request.url.path,
        }

    return create_exception_response(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        message="服务器内部错误",
        error_data=error_data,
    )


# ----------------------------------------------------------------------
# 3. 集中注册工厂函数
# ----------------------------------------------------------------------


def register_exception_handlers(app: FastAPI) -> None:
    """集中挂载所有全局异常处理器到 FastAPI 应用。

    Args:
        app: FastAPI 应用实例。
    """

    # 注册 HTTP 异常处理器。
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    # 注册请求参数校验异常处理器。
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    # 注册数据库完整性异常处理器。
    app.add_exception_handler(IntegrityError, integrity_error_handler)
    # 注册通用数据库异常处理器。
    app.add_exception_handler(SQLAlchemyError, sqlalchemy_error_handler)
    # 注册未知异常兜底处理器。
    app.add_exception_handler(Exception, general_exception_handler)
