"""接口响应缓存键、命中和主动失效行为测试。"""

import asyncio

from fastapi import FastAPI
from fastapi.testclient import TestClient
from fastapi_cache import FastAPICache
from fastapi_cache.backends.inmemory import InMemoryBackend
from fastapi_cache.decorator import cache

from app.core.cache import clear_cache_namespaces, request_cache_key_builder
from app.schemas.base import ResponseModel


def test_cached_route_uses_normalized_query_and_can_be_cleared() -> None:
    """等价查询应命中同一缓存，主动清理后应重新执行接口函数。"""

    FastAPICache.reset()
    FastAPICache.init(InMemoryBackend(), prefix="test-cache")

    application = FastAPI()
    call_count = 0

    @application.get("/cached")
    @cache(
        expire=60,
        namespace="example",
        key_builder=request_cache_key_builder,
    )
    async def cached_value() -> ResponseModel[dict[str, int]]:
        nonlocal call_count
        call_count += 1
        return ResponseModel(data={"call_count": call_count})

    try:
        with TestClient(application) as client:
            first_response = client.get("/cached?department_id=1&page=2")
            second_response = client.get("/cached?page=2&department_id=1")

            assert first_response.status_code == 200
            assert second_response.status_code == 200
            assert first_response.headers["x-fastapi-cache"] == "MISS"
            assert second_response.headers["x-fastapi-cache"] == "HIT"
            assert second_response.json()["data"]["call_count"] == 1
            assert call_count == 1

            asyncio.run(clear_cache_namespaces("example"))
            third_response = client.get("/cached?page=2&department_id=1")

            assert third_response.headers["x-fastapi-cache"] == "MISS"
            assert third_response.json()["data"]["call_count"] == 2
            assert call_count == 2
    finally:
        FastAPICache.reset()
