"""员工认证 API 路由。"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies.db import get_db
from app.schemas.auth_requests import AuthLoginRequest
from app.schemas.auth_responses import AuthLoginResponse
from app.schemas.base import ResponseModel
from app.services.auth import auth_login_service

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


__all__ = ["auth_router"]
