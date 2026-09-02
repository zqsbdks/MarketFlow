"""员工登录接口的响应模型。"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import EmployeeRole


# region 员工部门信息
class AuthDepartmentResponse(BaseModel):
    """认证接口中使用的员工所属部门公开信息。"""

    id: int = Field(..., description="部门ID")
    name: str = Field(..., description="部门名称", min_length=1, max_length=50)

    model_config = ConfigDict(from_attributes=True)
# endregion


# region 登录员工信息
class AuthLoginEmployee(BaseModel):
    """登录响应中的员工公开信息。"""

    id: int = Field(..., description="员工ID")
    employee_no: str = Field(..., description="员工编号", min_length=3, max_length=20)
    name: str = Field(..., description="员工姓名", min_length=1, max_length=50)
    role: EmployeeRole = Field(..., description="员工角色")
    department: AuthDepartmentResponse | None = Field(None, description="所属部门信息")
    must_change_password: bool = Field(..., description="是否需要修改密码")

    model_config = ConfigDict(from_attributes=True)
# endregion


# region 登录响应模型
class AuthLoginResponse(BaseModel):
    """登录成功后返回的访问令牌与员工信息。"""

    access_token: str
    token_type: Literal["bearer"] = "bearer"
    employee: AuthLoginEmployee
# endregion


# region 当前员工信息
class AuthMeResponse(BaseModel):
    """获取当前登录员工信息的响应模型。"""

    id: int = Field(..., description="员工ID")
    employee_no: str = Field(..., description="员工编号", min_length=3, max_length=20)
    name: str = Field(..., description="员工姓名", min_length=1, max_length=50)
    role: EmployeeRole = Field(..., description="员工角色")
    department: AuthDepartmentResponse | None = Field(None, description="所属部门信息")
    is_active: bool = Field(..., description="账号是否激活")

    model_config = ConfigDict(from_attributes=True)
# endregion

__all__ = [
    "AuthDepartmentResponse",
    "AuthLoginEmployee",
    "AuthLoginResponse",
    "AuthMeResponse",
]
