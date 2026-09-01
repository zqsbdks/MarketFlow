"""通过 TestClient 验证应用工厂、基础路由和统一响应格式。"""

from fastapi import Depends
from fastapi.testclient import TestClient

from app.dependencies.auth import get_current_token_payload
from app.main import create_app


def test_root() -> None:
    """根路径应返回标准成功响应和欢迎信息。"""

    # 上下文管理器会触发与真实服务器一致的 lifespan 启动和关闭流程。
    with TestClient(create_app()) as client:
        response = client.get("/")

    assert response.status_code == 200
    assert response.json() == {
        "code": 200,
        "message": "success",
        "data": {"message": "Hello World"},
    }


def test_health() -> None:
    """健康检查应返回 HTTP 200 和可机器识别的 ok 状态。"""

    with TestClient(create_app()) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["data"] == {"status": "ok"}


def test_liveness() -> None:
    """存活检查不应依赖数据库或 Redis。"""

    with TestClient(create_app()) as client:
        response = client.get("/health/live")

    assert response.status_code == 200
    assert response.json()["data"] == {"status": "ok"}


def test_readiness_reports_dependencies(monkeypatch) -> None:
    """依赖可用时，就绪检查应返回各组件状态。"""

    async def ready() -> dict[str, str]:
        return {"database": "ok", "redis": "disabled", "status": "ok"}

    monkeypatch.setattr("app.main.check_readiness", ready)
    with TestClient(create_app()) as client:
        response = client.get("/health/ready")

    assert response.status_code == 200
    assert response.json()["data"]["database"] == "ok"


def test_readiness_returns_503_when_database_fails(monkeypatch) -> None:
    """核心依赖不可用时，就绪检查必须返回 503。"""

    async def not_ready() -> dict[str, str]:
        return {"database": "error", "redis": "disabled", "status": "error"}

    monkeypatch.setattr("app.main.check_readiness", not_ready)
    with TestClient(create_app()) as client:
        response = client.get("/health/ready")

    assert response.status_code == 503
    assert response.json()["data"]["database"] == "error"


def test_authentication_challenge_header_is_preserved() -> None:
    """全局异常包装不能丢失 Bearer 认证挑战头。"""

    application = create_app()

    @application.get("/protected")
    async def protected(payload=Depends(get_current_token_payload)):
        return payload

    with TestClient(application) as client:
        response = client.get("/protected")

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_not_found_uses_standard_response() -> None:
    """不存在的路径也应经过全局异常处理器统一包装。"""

    with TestClient(create_app()) as client:
        response = client.get("/does-not-exist")

    assert response.status_code == 404
    assert response.json() == {
        "code": 404,
        "message": "Not Found",
        "data": None,
    }
