"""SQLAlchemy 声明式基类和公共时间字段。

所有 ORM 模型必须继承同一个 ``Base``，以便 Alembic 一次读取完整元数据。
"""

from datetime import datetime

from sqlalchemy import DateTime, FetchedValue, func, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """项目内所有 ORM 实体共用的声明式基类。

    业务模型必须继承本类，不能各自创建新的 ``DeclarativeBase``，否则 Alembic
    无法从一份 ``metadata`` 中发现所有表。
    """

    # 当前基类不强制公共列；用户可按业务需要在此加入命名约定或通用 Mixin。
    pass


class CreatedAtMixin:
    """为需要记录创建时间的表提供数据库端默认值。"""

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.current_timestamp(),
    )


class TimestampMixin(CreatedAtMixin):
    """为可修改的主数据表提供创建时间和更新时间。"""

    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"),
        server_onupdate=FetchedValue(),
        onupdate=func.current_timestamp(),
    )


__all__ = ["Base", "CreatedAtMixin", "TimestampMixin"]
