"""部门查询的数据访问函数。"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.department import Department


# region 获取部门列表
async def get_departments_list(db: AsyncSession) -> list[Department]:
    """按照部门 ID 升序查询全部部门。"""

    statement = select(Department).order_by(Department.id.asc())
    result = await db.scalars(statement)
    return list(result.all())


# endregion


__all__ = ["get_departments_list"]
