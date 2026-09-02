"""员工管理接口的响应模型。"""

from pydantic import BaseModel, ConfigDict, Field


# region 创建员工响应
class EmployeesCreateResponse(BaseModel):
    """创建成功后返回的员工编号和一次性临时密码。"""

    id: int = Field(..., description="员工ID", ge=1)
    employee_no: str = Field(
        ...,
        description="员工编号",
        min_length=1,
        max_length=20,
    )
    temporary_password: str = Field(
        "123456",
        description="临时密码",
        min_length=1,
        max_length=20,
    )
    must_change_password: bool = Field(
        True,
        description="是否需要修改密码",
    )

    model_config = ConfigDict(from_attributes=True)
# endregion


__all__ = ["EmployeesCreateResponse"]
