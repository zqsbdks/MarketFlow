"""员工管理业务逻辑。"""

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.crud.auth import get_employee_by_id
from app.crud.employees import (
    create_employee,
    get_department_by_id,
    get_list_employees,
    update_employee_status,
)
from app.models.enums import EmployeeRole
from app.schemas.employees_responses import (
    EmployeesCreateResponse,
    EmployeesItemResponse,
    EmployeesListResponse,
    EmployeesStatusUpdateResponse,
)

DEFAULT_EMPLOYEE_PASSWORD = "123456"


# region 创建员工
async def create_employee_service(
    name: str,
    role: EmployeeRole,
    department_id: int | None,
    current_employee_id: int,
    db: AsyncSession,
) -> EmployeesCreateResponse:
    """验证店长权限和部门规则后创建员工。"""

    current_employee = await get_employee_by_id(
        employee_id=current_employee_id,
        db=db,
    )
    if current_employee is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="当前登录员工不存在",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not current_employee.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="账号已停用",
        )

    if current_employee.must_change_password:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="请先修改初始密码",
        )

    if current_employee.role != EmployeeRole.STORE_MANAGER:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="只有店长可以创建员工",
        )

    if role != EmployeeRole.STORE_MANAGER and department_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="正式员工和契约工必须选择所属部门",
        )

    if department_id is not None:
        department = await get_department_by_id(department_id=department_id, db=db)
        if department is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="部门不存在",
            )
        if not department.is_active:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="部门已停用",
            )

    password_hash = hash_password(DEFAULT_EMPLOYEE_PASSWORD)
    new_employee = await create_employee(
        name=name,
        role=role,
        department_id=department_id,
        password_hash=password_hash,
        db=db,
    )

    await db.commit()

    return EmployeesCreateResponse(
        id=new_employee.id,
        employee_no=new_employee.employee_no,
        temporary_password=DEFAULT_EMPLOYEE_PASSWORD,
        must_change_password=new_employee.must_change_password,
    )


# endregion


# region 获取员工列表
async def get_list_employees_service(
    page: int,
    page_size: int,
    department_id: int | None,
    role: EmployeeRole | None,
    is_active: bool | None,
    current_employee_id: int,
    db: AsyncSession,
) -> EmployeesListResponse:
    """验证店长权限，并返回经过筛选和分页的员工列表。"""

    current_employee = await get_employee_by_id(
        employee_id=current_employee_id,
        db=db,
    )
    if current_employee is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="当前登录员工不存在",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not current_employee.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="账号已停用",
        )

    if current_employee.must_change_password:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="请先修改初始密码",
        )

    if current_employee.role != EmployeeRole.STORE_MANAGER:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="只有店长可以查看员工列表",
        )

    employees, total = await get_list_employees(
        page=page,
        page_size=page_size,
        department_id=department_id,
        role=role,
        is_active=is_active,
        db=db,
    )

    items = []
    for employee in employees:
        department_name = None
        if employee.department is not None:
            department_name = employee.department.name

        items.append(
            EmployeesItemResponse(
                id=employee.id,
                employee_no=employee.employee_no,
                name=employee.name,
                role=employee.role,
                department_name=department_name,
                is_active=employee.is_active,
            )
        )

    total_pages = (total + page_size - 1) // page_size

    return EmployeesListResponse(
        items=items,
        page=page,
        page_size=page_size,
        total=total,
        total_pages=total_pages,
    )


# endregion


# region 修改员工状态
async def update_employee_status_service(
    employee_id: int,
    is_active: bool,
    current_employee_id: int,
    db: AsyncSession,
) -> EmployeesStatusUpdateResponse:
    """验证店长权限，并更新指定员工的状态。"""

    current_employee = await get_employee_by_id(
        employee_id=current_employee_id,
        db=db,
    )
    if current_employee is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="当前登录员工不存在",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not current_employee.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="账号已停用",
        )

    if current_employee.must_change_password:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="请先修改初始密码",
        )

    if current_employee.role != EmployeeRole.STORE_MANAGER:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="只有店长可以修改员工状态",
        )

    if employee_id == current_employee_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="不能修改自己的账号状态",
        )

    employee = await get_employee_by_id(employee_id=employee_id, db=db)
    if employee is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="员工不存在",
        )

    await update_employee_status(
        employee=employee,
        is_active=is_active,
        db=db,
    )
    await db.commit()

    return EmployeesStatusUpdateResponse(
        id=employee.id,
        is_active=employee.is_active,
    )


# endregion

__all__ = [
    "DEFAULT_EMPLOYEE_PASSWORD",
    "create_employee_service",
    "get_list_employees_service",
    "update_employee_status_service",
]
