"""员工管理业务逻辑。"""

from datetime import date

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.crud.auth import get_employee_by_id
from app.crud.employees import (
    create_employee,
    get_department_by_id,
    get_employee_detail_by_id,
    get_list_employees,
    reset_employee_password,
    update_employee_detail,
    update_employee_status,
)
from app.models.enums import EmployeeRole, EmploymentStatus
from app.schemas.employees_requests import EmployeeDetailUpdateRequest
from app.schemas.employees_responses import (
    EmployeeDetailResponse,
    EmployeesCreateResponse,
    EmployeesItemResponse,
    EmployeesListResponse,
    EmployeesResetPasswordResponse,
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


# region 重置员工密码
async def reset_employee_password_service(
    employee_id: int,
    current_employee_id: int,
    db: AsyncSession,
) -> EmployeesResetPasswordResponse:
    """验证店长权限，并重置指定员工的密码。"""

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
            detail="只有店长可以重置员工密码",
        )

    if employee_id == current_employee_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="不能重置自己的密码",
        )

    employee = await get_employee_by_id(employee_id=employee_id, db=db)
    if employee is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="员工不存在",
        )

    temporary_password_hash = hash_password(DEFAULT_EMPLOYEE_PASSWORD)
    await reset_employee_password(
        employee=employee,
        password_hash=temporary_password_hash,
        db=db,
    )
    await db.commit()

    return EmployeesResetPasswordResponse(
        id=employee.id,
        temporary_password=DEFAULT_EMPLOYEE_PASSWORD,
        must_change_password=employee.must_change_password,
    )


# endregion


# region 获取员工详情
async def get_employee_detail_service(
    employee_id: int,
    current_employee_id: int,
    db: AsyncSession,
) -> EmployeeDetailResponse:
    """允许员工查看本人详情，并允许店长查看任意员工详情。"""

    # 先确认当前 Token 对应的员工账号仍然有效。
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
            detail="当前账号已停用",
        )

    if current_employee.must_change_password:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="请先修改初始密码",
        )

    # 普通员工只能查看本人；店长可以查看所有员工。
    if employee_id != current_employee_id and current_employee.role != EmployeeRole.STORE_MANAGER:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="只能查看自己的员工详情",
        )

    # 返回 EmployeeDetail ORM 对象或 None；对象内已加载 employee 和部门关系。
    employee_detail = await get_employee_detail_by_id(
        employee_id=employee_id,
        db=db,
    )
    if employee_detail is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="员工不存在或尚未创建员工详情",
        )

    # 取出关联的 Employee 对象，方便读取姓名、编号等账号字段；不会再次查询。
    employee = employee_detail.employee
    # 店长可能没有所属部门，此时返回 null，不能直接读取 department.name。
    department_name = None
    if employee.department is not None:
        department_name = employee.department.name

    # 将账号表和详情表的数据组装为平铺的响应模型。
    # 校验的是访问者状态，因此店长仍能查看已停用或未改初始密码的员工。
    return EmployeeDetailResponse(
        id=employee.id,
        employee_no=employee.employee_no,
        name=employee.name,
        role=employee.role,
        department_id=employee.department_id,
        department_name=department_name,
        is_active=employee.is_active,
        last_login_at=employee.last_login_at,
        gender=employee_detail.gender,
        phone=employee_detail.phone,
        birth_date=employee_detail.birth_date,
        hire_date=employee_detail.hire_date,
        address=employee_detail.address,
        employment_status=employee_detail.employment_status,
        separation_date=employee_detail.separation_date,
        separation_reason=employee_detail.separation_reason,
        # 这里返回详情记录的时间，而不是员工账号记录的时间。
        created_at=employee_detail.created_at,
        updated_at=employee_detail.updated_at,
    )


# endregion


# region 修改员工详情
async def update_employee_detail_service(
    employee_id: int,
    current_employee_id: int,
    request: EmployeeDetailUpdateRequest,
    db: AsyncSession,
) -> EmployeeDetailResponse:
    """验证店长权限和日期规则，在同一事务中更新并读取详情。

    employee_id：要修改的员工编号（数据库主键）。
    current_employee_id：当前登录的操作人编号（数据库主键）。
    request：这次提交的新资料；employee_detail：数据库中原来的资料。
    返回值：已经组装好的 EmployeeDetailResponse 响应对象。
    """

    # 验证操作人的账号，而不是被修改员工的账号。
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
            detail="当前账号已停用",
        )

    if current_employee.must_change_password:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="请先修改初始密码",
        )

    # 此表单包含入职日期、雇佣状态等人事字段，仅允许店长修改。
    if current_employee.role != EmployeeRole.STORE_MANAGER:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="只有店长可以修改员工详情",
        )

    # 出生日期不能晚于今天，也不能晚于入职日期。
    if request.birth_date > date.today() or request.birth_date > request.hire_date:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="出生日期不能晚于今天或入职日期",
        )

    # 取出本次填写的离职日期和原因；None 表示没有填写。
    # 单独保存日期，方便后面补上原日期或今天的日期。
    separation_date = request.separation_date
    separation_reason = request.separation_reason
    # not in 表示“不属于”：状态不是离职或解雇，却填写离职信息时拒绝。
    if request.employment_status not in (
        EmploymentStatus.RESIGNED,  # 离职
        EmploymentStatus.DISMISSED,  # 解雇
    ) and (separation_date is not None or separation_reason):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="在职或休假状态不能填写离职日期和原因",
        )

    # 读取被修改员工的旧资料；后面需要使用原状态和原离职日期。
    employee_detail = await get_employee_detail_by_id(
        employee_id=employee_id,
        db=db,
    )
    if employee_detail is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="员工不存在或尚未创建员工详情",
        )

    # 本次状态是离职或解雇时，才需要补离职日期；已经传日期则直接使用。
    if request.employment_status in (EmploymentStatus.RESIGNED, EmploymentStatus.DISMISSED):
        if separation_date is None:
            # 旧状态 == 新状态：例如原来已离职，这次只改电话，保留原日期。
            if employee_detail.employment_status == request.employment_status:
                separation_date = employee_detail.separation_date
            # 状态改变或原日期也为空时，使用今天。
            if separation_date is None:
                separation_date = date.today()
    # 有离职日期时才比较；离职可以和入职同一天，但不能更早。
    if separation_date is not None and separation_date < request.hire_date:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="离职或解雇日期不能早于入职日期",
        )

    # CRUD 只执行更新；复用详情查询获得最新字段，提交由本 Service 负责。
    await update_employee_detail(
        employee_id=employee_id,
        gender=request.gender,
        birth_date=request.birth_date,
        hire_date=request.hire_date,
        phone=request.phone,
        address=request.address,
        employment_status=request.employment_status,
        separation_date=separation_date,
        separation_reason=separation_reason,
        db=db,
    )
    # 复用获取详情的 Service：它会查询最新资料并组装响应，无需重复拼字段。
    # response 是 EmployeeDetailResponse 对象，不是数据库执行结果。
    response = await get_employee_detail_service(
        employee_id=employee_id,
        current_employee_id=current_employee_id,
        db=db,
    )
    # 上面的更新仍在当前事务里；提交成功后才能向前端返回成功结果。
    await db.commit()
    return response


# endregion

__all__ = [
    "DEFAULT_EMPLOYEE_PASSWORD",
    "create_employee_service",
    "get_employee_detail_service",
    "update_employee_detail_service",
    "get_list_employees_service",
    "reset_employee_password_service",
    "update_employee_status_service",
]
