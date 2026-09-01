"""SQLAlchemy 声明式基类。

所有 ORM 模型必须继承同一个 ``Base``，以便 Alembic 一次读取完整元数据。
"""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """项目内所有 ORM 实体共用的声明式基类。

    业务模型必须继承本类，不能各自创建新的 ``DeclarativeBase``，否则 Alembic
    无法从一份 ``metadata`` 中发现所有表。
    """

    # 当前基类不强制公共列；用户可按业务需要在此加入命名约定或通用 Mixin。
    pass
