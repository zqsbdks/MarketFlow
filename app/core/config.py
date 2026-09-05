"""应用配置加载模块。

配置由 Pydantic Settings 统一解析。进程环境变量优先于项目根目录的 ``.env``，
因此同一份代码可以在本地、测试和生产环境使用不同配置而无需改动源码。
"""

from functools import lru_cache
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """定义应用与 Alembic 共同使用的强类型运行配置。

    环境变量统一使用 ``APP_`` 前缀。例如字段 ``database_url`` 对应
    ``APP_DATABASE_URL``。未知字段被忽略，便于在共享环境文件中存放其他服务配置。
    """

    # 这里控制配置来源、编码和变量名前缀，不包含任何真实密码或密钥。
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="APP_",
        case_sensitive=False,
        extra="ignore",
    )

    environment: Literal["development", "test", "production"] = "development"
    project_name: str = "MarketFlow"  # OpenAPI 文档和日志中显示的项目名。
    debug: bool = False  # 生产环境必须关闭，避免响应中泄露调试信息。
    api_v1_prefix: str = "/api/v1"  # 业务 API 的统一版本前缀。

    # URL 必须使用 aiomysql 异步驱动；echo=True 时 SQL 会写入日志。
    database_url: str = (
        "mysql+aiomysql://username:password@localhost:3306/MarketFlowDB?charset=utf8mb4"
    )
    database_echo: bool = False

    # log_file 留空时只输出到控制台，设置路径后同时写入轮转文件。
    log_level: str = "INFO"
    log_file: str | None = None

    # secret_key 用于 JWT HMAC 签名，生产环境应使用至少 32 字节的随机值。
    secret_key: str = Field(default="dev-only-change-me-before-production", min_length=32)
    jwt_algorithm: Literal["HS256", "HS384", "HS512"] = "HS256"
    access_token_expire_minutes: int = Field(default=7 * 24 * 60, gt=0)

    # 仅供手动执行初始店长创建脚本使用，不在应用启动时自动创建账号。
    initial_manager_password: str | None = Field(default=None, min_length=6)

    # Redis 是可选服务；URL 为空时不会创建客户端或初始化缓存后端。
    redis_url: str | None = None
    redis_max_connections: int = Field(default=10, ge=1)
    redis_timeout: float = Field(default=5.0, gt=0)

    # default_factory 确保不同 Settings 实例不会共享同一个可变列表。
    cors_origins: list[str] = Field(default_factory=lambda: ["*"])

    @model_validator(mode="after")
    def validate_production_safety(self) -> "Settings":
        """阻止带有明显开发配置的应用以生产模式启动。"""

        if self.environment != "production":
            return self

        unsafe_options: list[str] = []
        if self.debug:
            unsafe_options.append("APP_DEBUG 必须为 false")
        if self.database_echo:
            unsafe_options.append("APP_DATABASE_ECHO 必须为 false")
        if self.secret_key == "dev-only-change-me-before-production":
            unsafe_options.append("APP_SECRET_KEY 必须替换为随机密钥")
        if "*" in self.cors_origins:
            unsafe_options.append("APP_CORS_ORIGINS 不能包含通配符 *")
        if unsafe_options:
            raise ValueError("生产环境配置不安全：" + "；".join(unsafe_options))
        return self


@lru_cache
def get_settings() -> Settings:
    """创建并缓存当前进程唯一的配置对象。

    缓存可以避免每次依赖注入时重复读取和解析 ``.env``。测试若需要重新加载配置，
    可以调用 ``get_settings.cache_clear()`` 后再获取。
    """

    return Settings()


# 绝大多数模块直接复用该实例，保证数据库、JWT 和 Alembic 读取相同配置。
settings = get_settings()
