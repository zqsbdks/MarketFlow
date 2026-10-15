"""员工登录业务逻辑。"""

from fastapi import HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.business_time import business_now
from app.core.security import hash_password, verify_password
from app.core.token import create_access_token
from app.crud.auth import (
    get_employee_by_employee_no,
    get_employee_by_id,
    update_employee_last_login,
)
from app.crud.operation_audit_logs import create_operation_audit_log
from app.crud.stores import first_active_store_id, get_store_by_id
from app.models.enums import EmployeeRole
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

    login_time = business_now()
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
        store_id=employee.store_id,
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
async def get_current_employee_info_service(
    employee_id: int, db: AsyncSession, *, http_request: Request | None = None
) -> AuthMeResponse:
    """查询当前员工及其部门，并组装公开信息。"""

    # 本接口在服务层明确检查店铺范围；不依赖数据库自动事件。
    if http_request is not None:
        access_employee = await get_employee_by_id(employee_id=employee_id, db=db)
        if access_employee is None or not access_employee.is_active:
            raise HTTPException(401, "账号不存在或已停用")
        is_headquarters = access_employee.role == EmployeeRole.HEADQUARTERS
        selected_store_id = access_employee.store_id
        raw_store_id = http_request.headers.get("X-Store-ID")
        if not raw_store_id:
            raw_store_id = http_request.query_params.get("store_id")
        if raw_store_id == "all":
            raise HTTPException(403, "此接口不支持全公司汇总")
        elif raw_store_id:
            try:
                selected_store_id = int(raw_store_id)
            except ValueError as error:
                raise HTTPException(422, "门店ID无效") from error
            if selected_store_id <= 0:
                raise HTTPException(422, "门店ID无效")
        if selected_store_id is None and is_headquarters and raw_store_id != "all":
            selected_store_id = await first_active_store_id(db)
        if selected_store_id is not None:
            selected_store = await get_store_by_id(selected_store_id, db)
            if selected_store is None or not selected_store.is_active:
                raise HTTPException(403, "门店不存在或已停用")
        if not is_headquarters and access_employee.store_id is None:
            raise HTTPException(403, "员工尚未分配门店")

        # 这里只记录本次查询参数；CRUD 会明确读取并添加 store_id 条件。
        db.info.update(
            actor_id=access_employee.id,
            actor_role=access_employee.role,
            own_store_id=access_employee.store_id,
            read_store_id=selected_store_id,
            write_store_id=access_employee.store_id,
            company_management=False,
            company_catalog_read=False,
            private_employee_path=False,
            store_context=True,
        )
        http_request.state.store_id = selected_store_id
        http_request.state.employee_id = access_employee.id
        http_request.state.own_store_id = access_employee.store_id

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
        store_id=employee.store_id,
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
    reason: str | None = None,
    *,
    http_request: Request | None = None,
) -> None:
    """修改当前登录员工密码。"""

    # 本接口在服务层明确检查店铺范围；不依赖数据库自动事件。
    if http_request is not None:
        access_employee = await get_employee_by_id(employee_id=employee_id, db=db)
        if access_employee is None or not access_employee.is_active:
            raise HTTPException(401, "账号不存在或已停用")
        is_headquarters = access_employee.role == EmployeeRole.HEADQUARTERS
        selected_store_id = access_employee.store_id
        raw_store_id = http_request.headers.get("X-Store-ID")
        if not raw_store_id:
            raw_store_id = http_request.query_params.get("store_id")
        if raw_store_id == "all":
            raise HTTPException(403, "此接口不支持全公司汇总")
        elif raw_store_id:
            try:
                selected_store_id = int(raw_store_id)
            except ValueError as error:
                raise HTTPException(422, "门店ID无效") from error
            if selected_store_id <= 0:
                raise HTTPException(422, "门店ID无效")
        if selected_store_id is None and is_headquarters and raw_store_id != "all":
            selected_store_id = await first_active_store_id(db)
        if selected_store_id is not None:
            selected_store = await get_store_by_id(selected_store_id, db)
            if selected_store is None or not selected_store.is_active:
                raise HTTPException(403, "门店不存在或已停用")
        if not is_headquarters and access_employee.store_id is None:
            raise HTTPException(403, "员工尚未分配门店")

        # 这里只记录本次查询参数；CRUD 会明确读取并添加 store_id 条件。
        db.info.update(
            actor_id=access_employee.id,
            actor_role=access_employee.role,
            own_store_id=access_employee.store_id,
            read_store_id=selected_store_id,
            write_store_id=access_employee.store_id,
            company_management=False,
            company_catalog_read=False,
            private_employee_path=False,
            store_context=True,
        )
        http_request.state.store_id = selected_store_id
        http_request.state.employee_id = access_employee.id
        http_request.state.own_store_id = access_employee.store_id

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

    # 密码属于敏感数据，审计记录只说明密码已修改，不保存密码或哈希值。
    await create_operation_audit_log(
        employee_id=employee_id,
        module="auth",
        action="change_password",
        target_type="employee",
        target_id=employee_id,
        before_data=None,
        after_data={"password_changed": True, "must_change_password": False},
        reason=reason,
        db=db,
    )

    await db.commit()


# endregion


__all__ = [
    "auth_login_service",
    "change_password_service",
    "get_current_employee_info_service",
]


async def get_verified_current_employee_id_service(current_employee_id, db) -> int:
    """在解析JWT后，继续检查员工账号的最新可用状态。

    缓存命中时路由函数本身不会再次执行，但 FastAPI 仍会先解析依赖。缓存接口使用
    本依赖，可以避免已停用或尚未修改初始密码的员工读取已有缓存。
    """
    employee = await get_employee_by_id(employee_id=current_employee_id, db=db)
    if employee is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="当前登录员工不存在",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not employee.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="账号已停用")
    if employee.must_change_password:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="请先修改初始密码")
    return employee.id


async def get_current_employee_id_service(token_payload, db) -> int:
    "从已验证的 JWT 载荷中取得数字类型的员工 ID。"
    try:
        employee_id = int(token_payload["sub"])
    except (KeyError, TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="访问令牌中的员工标识无效",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    employee = await get_employee_by_id(employee_id=employee_id, db=db)
    if employee is None or not employee.is_active:
        raise HTTPException(401, "账号不存在或已停用")
    return employee_id
