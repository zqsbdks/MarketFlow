"""员工管理接口的响应模型。"""

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import EmployeeGender, EmployeeRole, EmploymentStatus


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


# region 员工列表项
class EmployeesItemResponse(BaseModel):
    """员工列表中的单个员工公开信息。"""

    id: int = Field(..., description="员工ID", ge=1)
    employee_no: str = Field(
        ...,
        description="员工编号",
        min_length=1,
        max_length=20,
    )
    name: str = Field(..., description="员工姓名", min_length=1, max_length=50)
    role: EmployeeRole = Field(..., description="员工角色")
    department_name: str | None = Field(None, description="所属部门名称")
    is_active: bool = Field(..., description="是否启用")

    model_config = ConfigDict(from_attributes=True)


# endregion


# region 员工列表响应
class EmployeesListResponse(BaseModel):
    """员工列表及分页信息。"""

    items: list[EmployeesItemResponse] = Field(..., description="员工列表")
    page: int = Field(..., description="当前页码", ge=1)
    page_size: int = Field(..., description="每页数量", ge=1)
    total: int = Field(..., description="员工总数", ge=0)
    total_pages: int = Field(..., description="总页数", ge=0)

    model_config = ConfigDict(from_attributes=True)


# endregion


# region 修改员工状态响应
class EmployeesStatusUpdateResponse(BaseModel):
    """状态修改成功后的员工 ID 和最新状态。"""

    id: int = Field(..., description="员工ID", ge=1)
    is_active: bool = Field(..., description="是否启用")

    model_config = ConfigDict(from_attributes=True)


# endregion


# region 重置员工密码响应
class EmployeesResetPasswordResponse(BaseModel):
    """重置成功后返回员工 ID、临时密码和首次修改标记。"""

    id: int = Field(..., description="员工ID", ge=1)
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


# region 获取员工详情响应


class EmployeeDetailResponse(BaseModel):
    """员工详情响应。"""

    id: int = Field(..., description="员工ID", ge=1)
    employee_no: str = Field(
        ...,
        description="员工编号",
        min_length=1,
        max_length=20,
    )
    name: str = Field(
        ...,
        description="员工姓名",
        min_length=1,
        max_length=50,
    )
    role: EmployeeRole = Field(..., description="员工工种")

    # 店长可以没有所属部门，因此需要允许为空。
    department_id: int | None = Field(None, description="部门ID")
    department_name: str | None = Field(None, description="部门名称")

    is_active: bool = Field(..., description="账号是否启用")
    last_login_at: datetime | None = Field(None, description="最后登录时间")

    gender: EmployeeGender = Field(..., description="性别")
    phone: str | None = Field(
        None,
        description="联系电话",
        max_length=30,
    )
    birth_date: date | None = Field(None, description="出生日期")
    hire_date: date = Field(..., description="入职日期")
    address: str | None = Field(
        None,
        description="居住地址",
        max_length=255,
    )

    employment_status: EmploymentStatus = Field(..., description="雇佣状态")
    separation_date: date | None = Field(None, description="离职或解雇日期")
    separation_reason: str | None = Field(
        None,
        description="离职或解雇原因",
        max_length=255,
    )

    created_at: datetime = Field(..., description="详情创建时间")
    updated_at: datetime = Field(..., description="详情更新时间")

    model_config = ConfigDict(from_attributes=True)


# endregion


__all__ = [
    "EmployeeDetailResponse",
    "EmployeesCreateResponse",
    "EmployeesItemResponse",
    "EmployeesListResponse",
    "EmployeesResetPasswordResponse",
    "EmployeesStatusUpdateResponse",
]
