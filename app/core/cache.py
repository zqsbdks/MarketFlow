"""接口响应缓存的公共配置、缓存键生成和失效处理。"""

import hashlib
import inspect
import json
import logging
from collections.abc import Awaitable, Callable
from datetime import date, datetime, time
from functools import wraps
from typing import Any, ParamSpec, TypeVar, get_type_hints
from urllib.parse import urlencode

from fastapi import Request, Response
from fastapi_cache import FastAPICache
from pydantic import TypeAdapter
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.business_time import business_now

logger = logging.getLogger(__name__)

# 不同数据使用独立命名空间。修改某类数据时，只清除对应缓存，避免影响其他接口。
DEPARTMENTS_CACHE_NAMESPACE = "departments"
CATEGORIES_CACHE_NAMESPACE = "categories"
SUPPLIERS_CACHE_NAMESPACE = "suppliers"
SUPPLIER_PRODUCTS_CACHE_NAMESPACE = "supplier-products"
FORECAST_CACHE_NAMESPACE = "sales-forecast-v1"
REPORTS_CACHE_NAMESPACE = "historical-reports-v1"

# 缓存时间按数据变化频率设置：越稳定的数据缓存时间越长。
DEPARTMENTS_CACHE_SECONDS = 30 * 60
CATEGORIES_CACHE_SECONDS = 10 * 60
SUPPLIERS_CACHE_SECONDS = 5 * 60
SUPPLIER_PRODUCTS_CACHE_SECONDS = 3 * 60
FORECAST_CACHE_SECONDS = 24 * 60 * 60
REPORTS_CACHE_SECONDS = 3 * 60

P = ParamSpec("P")
T = TypeVar("T")


async def initialize_business_cache() -> None:
    """Web和独立调度器共用Redis；未配置或连接失败时使用进程内缓存。"""
    from fastapi_cache.backends.inmemory import InMemoryBackend
    from fastapi_cache.backends.redis import RedisBackend

    from app.core.redis import get_redis_client

    client = get_redis_client()
    if client is not None:
        try:
            await client.ping()
            FastAPICache.init(RedisBackend(client), prefix="fastapi-cache")
            return
        except Exception:
            logger.exception("Redis initialization failed; using in-memory cache")
    FastAPICache.init(InMemoryBackend(), prefix="fastapi-cache")


def historical_report(arguments: dict[str, Any]) -> bool:
    end = arguments.get("end_time") or arguments.get("end_date")
    if isinstance(end, datetime):
        return end < datetime.combine(business_now().date(), time.min)
    return isinstance(end, date) and end < business_now().date()


def business_cache(
    namespace: str,
    expire: int,
    *,
    enabled: Callable[[dict[str, Any]], bool] | None = None,
    shared_forecast: bool = False,
):
    """缓存纯查询结果；不缓存会话，不绕过上层权限校验，缓存故障回退数据库。"""

    def decorate(func: Callable[P, Awaitable[T]]) -> Callable[P, Awaitable[T]]:
        signature = inspect.signature(func)
        adapter = TypeAdapter(get_type_hints(func)["return"])

        @wraps(func)
        async def wrapped(*args: P.args, **kwargs: P.kwargs) -> T:
            bound = signature.bind(*args, **kwargs)
            bound.apply_defaults()
            arguments = bound.arguments
            if enabled is not None and not enabled(arguments):
                return await func(*args, **kwargs)
            db = arguments["db"]
            if not isinstance(db, AsyncSession):
                return await func(*args, **kwargs)
            if (
                shared_forecast
                and db.info.get("store_context")
                and db.info.get("read_store_id") != arguments["store_id"]
            ):
                return await func(*args, **kwargs)
            try:
                backend = FastAPICache.get_backend()
                prefix = FastAPICache.get_prefix()
                if not FastAPICache.get_enable():
                    return await func(*args, **kwargs)
            except AssertionError:
                return await func(*args, **kwargs)
            scope = (
                {}
                if shared_forecast
                else {
                    key: db.info.get(key)
                    for key in (
                        "read_store_id",
                        "actor_id",
                        "actor_role",
                        "own_store_id",
                        "store_context",
                        "company_catalog_read",
                    )
                }
            )
            payload = {
                "function": f"{func.__module__}.{func.__qualname__}",
                "scope": scope,
                "database": db.get_bind().engine.url.render_as_string(hide_password=True),
                "arguments": {key: value for key, value in arguments.items() if key != "db"},
            }
            digest = hashlib.sha256(
                json.dumps(payload, sort_keys=True, default=str).encode()
            ).hexdigest()
            key = f"{prefix}:{namespace}:{digest}"
            try:
                cached = await backend.get(key)
                if cached is not None:
                    return adapter.validate_json(cached)
            except Exception:
                logger.warning("Business cache read failed: %s", namespace, exc_info=True)
            result = await func(*args, **kwargs)
            try:
                await backend.set(key, adapter.dump_json(result), expire)
            except Exception:
                logger.warning("Business cache write failed: %s", namespace, exc_info=True)
            return result

        return wrapped

    return decorate


# region 生成接口缓存键
def request_cache_key_builder(
    func: Callable[..., Any],
    namespace: str = "",
    *,
    request: Request | None = None,
    response: Response | None = None,
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
) -> str:
    """根据请求方法、路径和查询参数生成稳定的缓存键。

    ``fastapi-cache`` 的默认缓存键会包含路由函数的全部参数，其中也包括每次请求
    都不同的 ``AsyncSession``。这里主动忽略数据库会话、响应对象等运行期参数，
    只保留真正决定查询结果的 URL 信息。
    """

    # 这些参数是 fastapi-cache 规定的函数签名；当前缓存键不需要读取它们。
    _ = (func, response, args, kwargs)

    if request is None:
        # 正常的 HTTP 接口都会提供 request；该分支用于直接调用被装饰函数的场景。
        return f"{namespace}:unknown-request"

    # 对查询参数排序，确保 ?page=1&page_size=20 和参数顺序不同的等价请求使用同一键。
    sorted_query_items = sorted(request.query_params.multi_items())
    normalized_query = urlencode(sorted_query_items, doseq=True)
    base_key = f"{namespace}:{request.method}:{request.url.path}"
    base_key += (
        f":store={getattr(request.state, 'store_id', None)}"
        f":employee={getattr(request.state, 'employee_id', None)}"
    )
    if normalized_query:
        return f"{base_key}?{normalized_query}"
    return base_key


# endregion


# region 清除业务缓存
async def clear_cache_namespaces(*namespaces: str) -> None:
    """清除一个或多个业务命名空间，并在缓存异常时保留主业务成功结果。

    数据库事务已经提交后，即使 Redis 临时不可用，也不应该把一次成功的创建或修改
    变成接口失败。因此缓存清除异常只写入日志，旧缓存仍会在较短的过期时间后消失。
    """

    for namespace in namespaces:
        try:
            await FastAPICache.clear(namespace=namespace)
        except Exception:
            logger.exception("Failed to clear cache namespace: %s", namespace)


# endregion


__all__ = [
    "CATEGORIES_CACHE_NAMESPACE",
    "CATEGORIES_CACHE_SECONDS",
    "DEPARTMENTS_CACHE_NAMESPACE",
    "DEPARTMENTS_CACHE_SECONDS",
    "FORECAST_CACHE_NAMESPACE",
    "FORECAST_CACHE_SECONDS",
    "REPORTS_CACHE_NAMESPACE",
    "REPORTS_CACHE_SECONDS",
    "SUPPLIERS_CACHE_NAMESPACE",
    "SUPPLIERS_CACHE_SECONDS",
    "SUPPLIER_PRODUCTS_CACHE_NAMESPACE",
    "SUPPLIER_PRODUCTS_CACHE_SECONDS",
    "clear_cache_namespaces",
    "business_cache",
    "historical_report",
    "initialize_business_cache",
    "request_cache_key_builder",
]
