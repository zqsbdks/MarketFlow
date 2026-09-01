"""核心基础设施包的公共入口。

这里只导出轻量配置对象；数据库、Redis 等资源应从对应模块按需导入，避免普通
包导入产生不必要的客户端初始化。
"""

from app.core.config import settings

__all__ = ["settings"]
