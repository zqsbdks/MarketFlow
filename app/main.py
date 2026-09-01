"""FastAPI 应用主入口模块。

本模块负责创建应用实例、注册全局中间件、挂载业务路由，并提供一个简单的根路径接口，
用于确认服务是否成功启动。
"""

from fastapi import FastAPI

from app.core.config import settings
from app.core.exceptions import create_exception_response, register_exception_handlers
from app.core.health import check_readiness
from app.core.lifespan import lifespan
from app.core.logging import configure_logging
from app.core.middlewares import register_middlewares
from app.routers import api_router
from app.schemas import ResponseModel


def create_app() -> FastAPI:
    """创建并配置一个彼此独立的 FastAPI 应用实例。

    使用工厂函数而不是只在模块顶层拼装应用，既方便 Uvicorn 加载全局 ``app``，
    也允许测试代码为每个用例创建全新的应用，避免路由和中间件状态相互污染。

    Returns:
        FastAPI: 已配置日志、中间件、异常处理、生命周期和业务路由的应用。
    """

    # 日志必须在其他运行期组件开始记录消息前完成配置。
    configure_logging()

    # lifespan 统一接管 Redis、数据库连接池等资源的启动与释放。
    application = FastAPI(
        title=settings.project_name,
        debug=settings.debug,
        lifespan=lifespan,
    )

    # 注册顺序集中放在应用工厂中，后续增加中间件或异常处理器时容易审查。
    register_middlewares(application)
    register_exception_handlers(application)

    # 所有业务路由统一带上版本前缀，例如 /api/v1/users。
    application.include_router(api_router, prefix=settings.api_v1_prefix)

    @application.get("/", response_model=ResponseModel[dict[str, str]])
    async def read_root() -> ResponseModel[dict[str, str]]:
        """返回基础欢迎信息，用于人工确认服务已经启动。"""

        return ResponseModel(data={"message": "Hello World"})

    @application.get("/health/live", response_model=ResponseModel[dict[str, str]])
    async def health_live() -> ResponseModel[dict[str, str]]:
        """存活检查不访问外部服务，只确认应用进程能够响应。"""

        return ResponseModel(data={"status": "ok"})

    @application.get("/health", response_model=ResponseModel[dict[str, str]])
    async def health_compatibility() -> ResponseModel[dict[str, str]]:
        """保留原健康检查地址，兼容已存在的监控配置。"""

        return ResponseModel(data={"status": "ok"})

    @application.get("/health/ready")
    async def health_ready():
        """检查数据库与已启用的 Redis 是否可以承接真实请求。"""

        report = await check_readiness()
        if report["status"] == "error":
            return create_exception_response(
                status_code=503,
                message="服务依赖尚未就绪",
                error_data=report,
            )
        return ResponseModel(data=report)

    return application


# Uvicorn 默认通过 ``app.main:app`` 导入此全局 ASGI 对象。
app = create_app()

# 运行服务命令：uvicorn app.main:app --reload
