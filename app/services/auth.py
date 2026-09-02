"""员工登录业务逻辑。"""

from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import verify_password
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


__all__ = ["auth_login_service", "get_current_employee_info_service"]
