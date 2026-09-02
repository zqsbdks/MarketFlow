"""员工认证 API 路由。"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies.auth import get_current_employee_id
from app.dependencies.db import get_db
from app.schemas.auth_requests import AuthLoginRequest, AuthPasswordChangeRequest
from app.schemas.auth_responses import AuthLoginResponse, AuthMeResponse
from app.schemas.base import ResponseModel
from app.services.auth import (
    auth_login_service,
    change_password_service,
    get_current_employee_info_service,
)

auth_router = APIRouter(tags=["auth"], prefix="/auth")


# region 员工登录接口
@auth_router.post(
    "/login",
    response_model=ResponseModel[AuthLoginResponse],
    summary="员工登录",
    description="使用员工编号和密码登录并返回 JWT 访问令牌。",
)
async def auth_login(
    request: AuthLoginRequest,
    db: AsyncSession = Depends(get_db),
) -> ResponseModel[AuthLoginResponse]:
    """验证员工凭据、账号状态，并返回统一格式的登录结果。"""

    login_result = await auth_login_service(
        employee_no=request.employee_no,
        password=request.password,
        db=db,
    )

    return ResponseModel[AuthLoginResponse](
        message="登录成功",
        data=login_result,
    )


# endregion


# region 获取当前员工信息接口
@auth_router.get(
    "/me",
    response_model=ResponseModel[AuthMeResponse],
    summary="获取当前登录员工信息",
)
async def get_current_employee_info(
    employee_id: int = Depends(get_current_employee_id),
    db: AsyncSession = Depends(get_db),
) -> ResponseModel[AuthMeResponse]:
    """根据 Token 中的员工 ID 返回当前员工公开信息。"""

    employee_info = await get_current_employee_info_service(
        employee_id=employee_id,
        db=db,
    )

    return ResponseModel[AuthMeResponse](
        message="获取当前登录员工信息成功",
        data=employee_info,
    )


# endregion


# region 修改密码接口
@auth_router.post(
    "/password",
    response_model=ResponseModel[None],
    summary="修改当前登录员工密码",
)
async def change_password(
    password: AuthPasswordChangeRequest,
    employee_id: int = Depends(get_current_employee_id),
    db: AsyncSession = Depends(get_db),
) -> ResponseModel[None]:
    """验证当前密码并更新为新密码。"""

    await change_password_service(
        employee_id=employee_id,
        old_password=password.old_password,
        new_password=password.new_password,
        confirm_password=password.confirm_password,
        db=db,
    )

    return ResponseModel[None](message="密码修改成功")


# endregion


__all__ = ["auth_router"]
