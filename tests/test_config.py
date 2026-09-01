"""验证 Settings 的数据库约束、默认值和可变字段隔离。"""

import pytest
from pydantic import ValidationError
from sqlalchemy.engine import make_url

from app.core.config import Settings


def test_default_database_is_marketflow_utf8mb4() -> None:
    """第一版默认连接 MarketFlowDB，并明确启用 utf8mb4。"""

    url = make_url(Settings(_env_file=None).database_url)

    assert url.database == "MarketFlowDB"
    assert url.query["charset"] == "utf8mb4"


def test_settings_accept_mysql_async_url() -> None:
    """显式传入的 aiomysql URL 应被保留，并继续带有默认 API 前缀。"""

    # _env_file=None 隔离开发机 .env，确保本测试只验证声明的输入和默认值。
    settings = Settings(
        _env_file=None,
        database_url="mysql+aiomysql://user:password@localhost/test",
    )

    assert settings.database_url.startswith("mysql+aiomysql://")
    assert settings.api_v1_prefix == "/api/v1"


def test_cors_origins_is_not_shared() -> None:
    """两个 Settings 实例不能共享同一个 CORS 列表对象。"""

    first = Settings(_env_file=None)
    second = Settings(_env_file=None)
    # 修改第一个实例后，第二个实例不应出现相同元素。
    first.cors_origins.append("https://example.com")

    assert "https://example.com" not in second.cors_origins


@pytest.mark.parametrize(
    ("unsafe_setting", "unsafe_value"),
    [
        ("debug", True),
        ("database_echo", True),
        ("secret_key", "dev-only-change-me-before-production"),
        ("cors_origins", ["*"]),
    ],
)
def test_production_rejects_unsafe_defaults(unsafe_setting: str, unsafe_value: object) -> None:
    """生产模式不能带着任一项明显的开发配置启动。"""

    safe_values: dict[str, object] = {
        "environment": "production",
        "debug": False,
        "database_echo": False,
        "secret_key": "production-test-secret-key-with-at-least-32-bytes",
        "cors_origins": ["https://app.example.com"],
    }
    safe_values[unsafe_setting] = unsafe_value

    with pytest.raises(ValidationError, match="生产环境配置不安全"):
        Settings(_env_file=None, **safe_values)


def test_production_accepts_safe_configuration() -> None:
    """全部安全约束满足时允许创建生产配置。"""

    settings = Settings(
        _env_file=None,
        environment="production",
        secret_key="production-test-secret-key-with-at-least-32-bytes",
        cors_origins=["https://app.example.com"],
    )

    assert settings.environment == "production"
