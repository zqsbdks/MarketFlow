"""FastAPI 公共依赖导出入口。

调用方可以从本包直接导入长名称 ``get_db_session``，也可以使用路由中更简洁的
``get_db``；二者指向同一个会话依赖。
"""

from app.core.database import get_db_session
from app.dependencies.auth import get_current_token_payload
from app.dependencies.db import get_db

__all__ = ["get_current_token_payload", "get_db", "get_db_session"]
