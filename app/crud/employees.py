"""员工管理相关的数据库读写函数。"""

from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.department import Department
from app.models.employee import Employee
from app.models.enums import EmployeeRole


# region 查询部门
async def get_department_by_id(
    department_id: int,
    db: AsyncSession,
) -> Department | None:
    """按主键查询部门。"""

    return await db.get(Department, department_id)
# endregion


# region 创建员工
async def create_employee(
    name: str,
    role: EmployeeRole,
    department_id: int | None,
    password_hash: str,
    db: AsyncSession,
) -> Employee:
    """创建一个新的员工记录。"""

    # employee_no 不允许为空，先使用事务内唯一的临时编号取得自增主键。
    temporary_employee_no = f"TMP-{uuid4().hex[:16]}"
    new_employee = Employee(
        employee_no=temporary_employee_no,
        name=name,
        role=role,
        department_id=department_id,
        password_hash=password_hash,
        must_change_password=True,
    )
    db.add(new_employee)

    # flush 后可取得自增 ID，再生成稳定且唯一的 E00001 格式员工编号。
    await db.flush()
    new_employee.employee_no = f"E{new_employee.id:05d}"
    await db.flush()

    return new_employee
# endregion


__all__ = ["create_employee", "get_department_by_id"]
