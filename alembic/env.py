"""Alembic 异步迁移运行环境。

本文件在执行 ``alembic`` 命令时由框架加载，负责绑定应用配置、ORM 元数据，
并分别实现离线 SQL 生成与在线数据库迁移流程。
"""

import asyncio
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context
from app.core.config import settings
from app.models import Base

# Alembic 在加载 env.py 前创建上下文；config 对象对应根目录 alembic.ini。
config = context.config

# 使用 alembic.ini 中的 logging 配置，确保命令行能显示迁移进度和错误。
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# 导入 app.models 会注册其中显式导出的 ORM 模型，metadata 用于自动生成差异。
target_metadata = Base.metadata

# 覆盖 ini 中的占位 URL，保证应用和迁移使用完全相同的数据库。URL 编码密码可能
# 包含百分号，必须替换成 %% 以免被 ConfigParser 当作插值语法。
config.set_main_option("sqlalchemy.url", settings.database_url.replace("%", "%%"))


def include_name(
    name: str | None,
    type_: str,
    parent_names: dict[str, str | None],
) -> bool:
    """判断数据库对象是否应进入 Alembic 自动差异比较。

    只自动管理当前项目 metadata 中声明的表，避免模板连接到共享或遗留数据库时，
    把其他项目的表误判成待删除对象。因此真正的删表操作必须手写迁移并人工复核。
    """

    if type_ == "table" and name is not None:
        # metadata 的键在指定 schema 时形如 "schema.table"，否则就是表名。
        schema_name = parent_names.get("schema_name")
        table_key = f"{schema_name}.{name}" if schema_name else name
        return table_key in target_metadata.tables
    return True


def run_migrations_offline() -> None:
    """离线生成迁移 SQL，而不建立真实数据库连接。

    ``--sql`` 模式会进入此分支。literal_binds 将参数直接渲染进 SQL，便于把输出
    交给 DBA 审核或在受控环境执行。
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,  # 比较列类型变化。
        compare_server_default=True,  # 比较数据库端默认值变化。
        render_as_batch=url.startswith("sqlite"),
        include_name=include_name,
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    """在已有同步连接上下文中执行实际迁移事务。

    Args:
        connection: 由异步连接通过 ``run_sync`` 提供的同步 SQLAlchemy 连接。
    """

    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
        render_as_batch=connection.dialect.name == "sqlite",
        include_name=include_name,
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """创建一次性异步 Engine，连接数据库并运行迁移。"""

    # NullPool 避免 Alembic 短命令进程维护无意义的长连接池。
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        # Alembic 的核心迁移 API 是同步的，通过 run_sync 安全桥接异步连接。
        await connection.run_sync(do_run_migrations)

    # 显式释放底层连接，避免命令结束时出现未关闭连接警告。
    await connectable.dispose()


def run_migrations_online() -> None:
    """从同步 Alembic 入口启动异步迁移事件循环。"""

    asyncio.run(run_async_migrations())


# Alembic 根据是否带 --sql 参数选择离线或在线执行路径。
if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
