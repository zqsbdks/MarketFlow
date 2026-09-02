"""数据库访问层包。

CRUD 函数只处理持久化查询与写入；跨多个仓储的业务流程应放在 Service 层，
避免路由直接堆积 SQLAlchemy 操作。
"""

from app.crud.auth import (
    get_employee_by_employee_no,
    get_employee_by_id,
    update_employee_last_login,
)

__all__ = [
    "get_employee_by_employee_no",
    "get_employee_by_id",
    "update_employee_last_login",
]
