"""员工登录相关的数据库读写函数。"""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.employee import Employee


# region 查询员工账号
async def get_employee_by_employee_no(
    employee_no: str,
    db: AsyncSession,
) -> Employee | None:
    """按员工编号查询单个员工账号。"""

    stmt = (
        select(Employee)
        .options(selectinload(Employee.department))
        .where(Employee.employee_no == employee_no)
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


# endregion


# region 更新最后登录时间
async def update_employee_last_login(
    employee: Employee,
    login_time: datetime,
    db: AsyncSession,
) -> None:
    """修改员工最后登录时间，并把变更发送到当前数据库事务。"""

    employee.last_login_at = login_time
    # flush 只把 SQL 发送到数据库，事务最终由 Service 统一提交或回滚。
    await db.flush()


# endregion


# region 按ID查询员工账号
async def get_employee_by_id(
    employee_id: int,
    db: AsyncSession,
) -> Employee | None:
    """按员工 ID 查询员工，并加载所属部门的 ID 和名称。"""

    stmt = (
        select(Employee)
        .options(selectinload(Employee.department))
        .where(Employee.id == employee_id)
    )
    result = await db.execute(stmt)
    employee = result.scalar_one_or_none()

    return employee


# endregion

__all__ = [
    "get_employee_by_employee_no",
    "get_employee_by_id",
    "update_employee_last_login",
]
