"""员工登录业务逻辑。"""

from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password, verify_password
from app.core.token import create_access_token
from app.crud.auth import (
    get_employee_by_employee_no,
    get_employee_by_id,
    update_employee_last_login,
)
from app.schemas.auth_responses import (
    AuthDepartmentResponse,
    AuthLoginEmployee,
    AuthLoginResponse,
    AuthMeResponse,
)


# region 员工登录
async def auth_login_service(
    employee_no: str,
    password: str,
    db: AsyncSession,
) -> AuthLoginResponse:
    """验证员工登录、签发 Token，并组装完整登录结果。"""

    employee = await get_employee_by_employee_no(employee_no=employee_no, db=db)
    if employee is None or not verify_password(password, employee.password_hash):
        # 对外统一表示凭据错误，避免泄露员工编号是否存在。
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="员工编号或密码错误",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not employee.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="账号已停用",
        )

    login_time = datetime.now(UTC).replace(tzinfo=None)
    await update_employee_last_login(
        employee=employee,
        login_time=login_time,
        db=db,
    )
    # Service 负责本次登录业务的事务边界。
    await db.commit()

    token = create_access_token(data={"sub": str(employee.id)})
    department_response = None
    if employee.department is not None:
        department_response = AuthDepartmentResponse(
            id=employee.department.id,
            name=employee.department.name,
        )

    employee_response = AuthLoginEmployee(
        id=employee.id,
        employee_no=employee.employee_no,
        name=employee.name,
        role=employee.role,
        department=department_response,
        must_change_password=employee.must_change_password,
    )

    return AuthLoginResponse(
        access_token=token,
        token_type="bearer",
        employee=employee_response,
    )


# endregion


# region 获取当前员工信息
async def get_current_employee_info_service(employee_id: int, db: AsyncSession) -> AuthMeResponse:
    """查询当前员工及其部门，并组装公开信息。"""

    employee = await get_employee_by_id(employee_id=employee_id, db=db)
    if employee is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="员工不存在",
        )

    department_response = None
    if employee.department is not None:
        department_response = AuthDepartmentResponse(
            id=employee.department.id,
            name=employee.department.name,
        )

    return AuthMeResponse(
        id=employee.id,
        employee_no=employee.employee_no,
        name=employee.name,
        role=employee.role,
        department=department_response,
        is_active=employee.is_active,
    )


# endregion


# region 修改当前员工密码
async def change_password_service(
    employee_id: int,
    old_password: str,
    new_password: str,
    confirm_password: str,
    db: AsyncSession,
) -> None:
    """修改当前登录员工密码。"""

    employee = await get_employee_by_id(employee_id=employee_id, db=db)
    if employee is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="员工不存在",
        )

    if not employee.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="账号已停用",
        )

    if not verify_password(old_password, employee.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="旧密码错误",
        )

    if new_password != confirm_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="两次输入的新密码不一致",
        )

    if verify_password(new_password, employee.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="新密码不能与旧密码相同",
        )

    # 更新密码哈希
    employee.password_hash = hash_password(new_password)
    # 标记不再需要修改密码
    employee.must_change_password = False

    await db.commit()


# endregion


__all__ = [
    "auth_login_service",
    "change_password_service",
    "get_current_employee_info_service",
]
