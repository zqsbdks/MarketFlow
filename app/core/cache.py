"""接口响应缓存的公共配置、缓存键生成和失效处理。"""

import logging
from collections.abc import Callable
from typing import Any
from urllib.parse import urlencode

from fastapi import Request, Response
from fastapi_cache import FastAPICache

logger = logging.getLogger(__name__)

# 不同数据使用独立命名空间。修改某类数据时，只清除对应缓存，避免影响其他接口。
DEPARTMENTS_CACHE_NAMESPACE = "departments"
CATEGORIES_CACHE_NAMESPACE = "categories"
SUPPLIERS_CACHE_NAMESPACE = "suppliers"
SUPPLIER_PRODUCTS_CACHE_NAMESPACE = "supplier-products"

# 缓存时间按数据变化频率设置：越稳定的数据缓存时间越长。
DEPARTMENTS_CACHE_SECONDS = 30 * 60
CATEGORIES_CACHE_SECONDS = 10 * 60
SUPPLIERS_CACHE_SECONDS = 5 * 60
SUPPLIER_PRODUCTS_CACHE_SECONDS = 3 * 60


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
    "SUPPLIERS_CACHE_NAMESPACE",
    "SUPPLIERS_CACHE_SECONDS",
    "SUPPLIER_PRODUCTS_CACHE_NAMESPACE",
    "SUPPLIER_PRODUCTS_CACHE_SECONDS",
    "clear_cache_namespaces",
    "request_cache_key_builder",
]
