"""SQLAlchemy 异步引擎、会话工厂和 FastAPI 数据库依赖。

本模块只负责连接与会话生命周期，不负责建表。数据库结构必须通过 ORM 模型和
Alembic 迁移管理，业务代码不应直接创建新的 Engine。
"""

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings
from app.models.base import Base

# 应用和 Alembic 均从 Settings 取得同一条异步数据库 URL。
ASYNC_DATABASE_URL = settings.database_url

# pool_pre_ping 在借出连接前检查存活状态，减少 MySQL 空闲连接失效错误。
engine_options: dict[str, object] = {
    "echo": settings.database_echo,
    "pool_pre_ping": True,
}
if not ASYNC_DATABASE_URL.startswith("sqlite"):
    # MySQL 使用有界连接池：10 个常驻连接，繁忙时最多临时增加 20 个。
    engine_options.update(pool_size=10, max_overflow=20)

# Engine 在整个进程中共享，由 lifespan 在应用关闭时统一 dispose。
async_engine = create_async_engine(ASYNC_DATABASE_URL, **engine_options)

# expire_on_commit=False 让已提交 ORM 对象在响应序列化阶段仍可读取属性。
async_session_factory = async_sessionmaker(
    bind=async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db_session() -> AsyncIterator[AsyncSession]:
    """为一次请求提供独立的异步数据库会话。

    正常结束时只关闭会话，不自动提交；业务 Service/CRUD 必须明确调用
    ``await session.commit()``。发生异常时先回滚当前事务，再把原异常继续抛出，
    交给全局异常处理器生成响应。

    Yields:
        AsyncSession: 绑定到共享异步 Engine 的请求级会话。
    """

    async with async_session_factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


# 明确公共接口，避免调用方依赖模块内部的临时配置变量。
__all__ = ["Base", "async_engine", "async_session_factory", "get_db_session"]
