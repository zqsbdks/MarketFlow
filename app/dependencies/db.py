"""数据库依赖注入模块。

该模块用于为路由函数提供异步数据库会话，并在请求结束后自动关闭会话，
避免手动管理数据库连接上下文。
"""

from app.core.database import get_db_session

# 简短名称供 ``Depends(get_db)`` 使用；赋值而非再包装一层生成器，确保回滚和
# 关闭逻辑始终只有 app.core.database 一份实现。
get_db = get_db_session

__all__ = ["get_db"]
