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
    configure_logging()  # 配置日志级别、控制台输出和可选的轮转文件输出。

    # lifespan 统一接管 Redis、数据库连接池等资源的启动与释放。
    application = FastAPI(
        title=settings.project_name,  # 接口文档显示的项目名称。
        version="2.1.0",  # 接口文档版本号，不会自动跟随 Git 标签更新。
        debug=settings.debug,  # 框架调试开关，生产环境必须关闭。
        lifespan=lifespan,  # 登记启动与关闭处理函数，此处不直接执行它。
    )

    # 注册顺序集中放在应用工厂中，后续增加中间件或异常处理器时容易审查。
    register_middlewares(application)  # 注册全局中间件，当前用于浏览器跨域访问。
    register_exception_handlers(application)  # 注册异常处理器，统一错误响应格式。

    # 所有业务路由统一带上版本前缀，例如 /api/v1/users。
    application.include_router(api_router, prefix=settings.api_v1_prefix)  # 挂载业务接口。

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

        report = await check_readiness()  # 检查数据库，以及已配置的 Redis 是否可用。
        if report["status"] == "error":  # 任一依赖异常时返回服务暂不可用的响应。
            return create_exception_response(
                status_code=503,  # 设置实际 HTTP 状态码。
                message="服务依赖尚未就绪",  # 返回给调用方的提示。
                error_data=report,  # 附上各依赖的检查结果。
            )
        return ResponseModel(data=report)  # 检查通过，使用统一的成功响应结构。

    return application  # 把组装好的应用对象交给调用者。


# Uvicorn 默认通过 ``app.main:app`` 导入此全局 ASGI 对象。
app = create_app()  # 模块导入时创建应用，供 Uvicorn 通过 app.main:app 加载。

# 运行服务命令：uvicorn app.main:app --reload
