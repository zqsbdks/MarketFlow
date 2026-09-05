"""员工管理相关的数据库读写函数。"""

from datetime import date
from uuid import uuid4

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.department import Department
from app.models.employee import Employee
from app.models.employee_detail import EmployeeDetail
from app.models.enums import EmployeeGender, EmployeeRole, EmploymentStatus


# region 查询部门
async def get_department_by_id(
    department_id: int,
    db: AsyncSession,
) -> Department | None:
    """按主键查询部门。"""

    return await db.get(Department, department_id)


# endregion


# region 查询员工列表
async def get_list_employees(
    page: int,
    page_size: int,
    department_id: int | None,
    role: EmployeeRole | None,
    is_active: bool | None,
    db: AsyncSession,
) -> tuple[list[Employee], int]:
    """按条件分页查询员工，并返回当前页记录和总数量。"""

    conditions = []
    if department_id is not None:
        conditions.append(Employee.department_id == department_id)
    if role is not None:
        conditions.append(Employee.role == role)
    if is_active is not None:
        conditions.append(Employee.is_active == is_active)

    count_stmt = select(func.count(Employee.id)).where(*conditions)
    count_result = await db.execute(count_stmt)
    total = count_result.scalar_one()

    offset = (page - 1) * page_size
    list_stmt = (
        select(Employee)
        .options(selectinload(Employee.department))
        .where(*conditions)
        .order_by(Employee.id)
        .offset(offset)
        .limit(page_size)
    )
    list_result = await db.execute(list_stmt)
    employees = list(list_result.scalars().all())

    return employees, total


# endregion


# region 获取员工详情
async def get_employee_detail_by_id(
    employee_id: int,
    db: AsyncSession,
) -> EmployeeDetail | None:
    """返回一个 EmployeeDetail 对象，查不到详情时返回 None。

    关联对象已提前加载，可通过 detail.employee 访问 Employee，
    通过 detail.employee.department 访问 Department（无部门时为 None）。
    """

    statement = (
        select(EmployeeDetail)
        .options(
            # 使用额外 SELECT 提前加载员工及部门关系，供 Service 读取。
            selectinload(EmployeeDetail.employee).selectinload(Employee.department),
        )
        .where(EmployeeDetail.employee_id == employee_id)
        # 修改后复用本查询时，刷新会话中已有对象及数据库生成的更新时间。
        .execution_options(populate_existing=True)
    )
    result = await db.execute(statement)

    # 从执行结果中取出唯一的详情 ORM 对象；没有记录时返回 None。
    return result.scalar_one_or_none()


# endregion


# region 修改员工详情
async def update_employee_detail(
    employee_id: int,
    gender: EmployeeGender,
    birth_date: date,
    hire_date: date,
    phone: str,
    address: str,
    employment_status: EmploymentStatus,
    separation_date: date | None,
    separation_reason: str | None,
    db: AsyncSession,
) -> None:
    """执行 UPDATE，不返回详情对象；查询结果与提交事务由 Service 负责。"""

    statement = (
        update(EmployeeDetail)
        .where(EmployeeDetail.employee_id == employee_id)
        .values(
            gender=gender,
            birth_date=birth_date,
            hire_date=hire_date,
            phone=phone,
            address=address,
            employment_status=employment_status,
            separation_date=separation_date,
            separation_reason=separation_reason,
        )
    )
    # execute 执行 UPDATE，其返回值是执行结果，不是 EmployeeDetail 对象。
    await db.execute(statement)


# endregion


# region 修改员工状态
async def update_employee_status(
    employee: Employee,
    is_active: bool,
    db: AsyncSession,
) -> Employee:
    """修改员工启用状态，并把变更发送到当前事务。"""

    employee.is_active = is_active
    # CRUD 只执行 flush，最终提交或回滚仍由 Service 控制。
    await db.flush()
    return employee


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
        detail=EmployeeDetail(hire_date=date.today()),
    )
    db.add(new_employee)

    # flush 后可取得自增 ID，再生成稳定且唯一的 E00001 格式员工编号。
    await db.flush()
    new_employee.employee_no = f"E{new_employee.id:05d}"
    await db.flush()

    return new_employee


# endregion


# region 重置员工密码
async def reset_employee_password(
    employee: Employee,
    password_hash: str,
    db: AsyncSession,
) -> Employee:
    """重置员工密码，并把变更发送到当前事务。"""

    employee.password_hash = password_hash
    employee.must_change_password = True
    # CRUD 只执行 flush，最终提交或回滚由 Service 控制。
    await db.flush()
    return employee


# endregion


__all__ = [
    "create_employee",
    "get_department_by_id",
    "get_employee_detail_by_id",
    "get_list_employees",
    "reset_employee_password",
    "update_employee_detail",
    "update_employee_status",
]
