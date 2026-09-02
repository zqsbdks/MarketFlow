"""员工认证接口的请求模型。"""

from pydantic import BaseModel, Field


# region 登录请求模型
class AuthLoginRequest(BaseModel):
    """员工登录请求。"""

    employee_no: str = Field(..., description="员工编号", min_length=3, max_length=20)
    password: str = Field(..., description="登录密码", min_length=3, max_length=128)
# endregion


# region 修改密码请求模型
class AuthPasswordChangeRequest(BaseModel):
    """员工修改密码请求。"""

    old_password: str = Field(..., description="旧密码", min_length=3, max_length=128)
    new_password: str = Field(..., description="新密码", min_length=3, max_length=128)
    confirm_password: str = Field(..., description="确认新密码", min_length=3, max_length=128)
# endregion


__all__ = ["AuthLoginRequest", "AuthPasswordChangeRequest"]
