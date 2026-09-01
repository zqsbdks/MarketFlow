"""ORM 模型集中注册入口。

Alembic 只会看到导入进 ``Base.metadata`` 的模型。新增模型后，应在本文件显式
重导出，例如 ``from app.models.user import User as User``，避免只创建文件却没有
生成迁移的问题。
"""

from app.models.base import Base

# 新增模型后同步加入 __all__，让包的公共接口保持清晰。
__all__ = ["Base"]
