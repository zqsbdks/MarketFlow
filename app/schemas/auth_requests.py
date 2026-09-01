"""员工登录接口的请求模型。"""

from pydantic import BaseModel, Field


# region 登录请求模型
class AuthLoginRequest(BaseModel):
    """员工登录请求。"""

    employee_no: str = Field(..., description="员工编号", min_length=3, max_length=20)
    password: str = Field(..., description="登录密码", min_length=3, max_length=128)
# endregion


__all__ = ["AuthLoginRequest"]
