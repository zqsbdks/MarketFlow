"""部门查询的数据访问函数。"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.department import Department
from app.models.store import StoreDepartment


# region 获取部门列表
async def get_departments_list(db: AsyncSession) -> list[Department]:
    """按照部门 ID 升序查询全部部门。"""
    statement = select(Department).order_by(Department.id.asc())
    if db.info.get("read_store_id") is not None and (not db.info.get("company_catalog_read")):
        enabled_departments = select(StoreDepartment.department_id).where(
            StoreDepartment.store_id == db.info["read_store_id"],
            StoreDepartment.is_active.is_(True),
        )
        statement = statement.where(Department.id.in_(enabled_departments))
    result = await db.scalars(statement)
    return list(result.all())


# endregion


__all__ = ["get_departments_list"]
