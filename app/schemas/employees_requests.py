"""员工管理接口的请求模型。"""

from datetime import date

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import EmployeeGender, EmployeeRole, EmploymentStatus


# region 创建员工请求
class EmployeesCreateRequest(BaseModel):
    """店长创建员工时提交的公开字段。"""

    name: str = Field(..., description="员工姓名", min_length=1, max_length=50)
    role: EmployeeRole = Field(..., description="员工角色")
    department_id: int | None = Field(None, description="所属部门ID", ge=1)

    # 自动清除字符串两端空格；只包含空格的姓名会因 min_length=1 被拒绝。
    model_config = ConfigDict(str_strip_whitespace=True)


# endregion


# region 员工列表请求
class EmployeesListRequest(BaseModel):
    """员工列表的分页及可选筛选条件。"""

    page: int = Field(1, description="页码", ge=1)
    page_size: int = Field(10, description="每页数量", ge=1, le=100)
    department_id: int | None = Field(None, description="所属部门ID", ge=1)
    role: EmployeeRole | None = Field(None, description="员工角色")
    is_active: bool | None = Field(None, description="是否启用")


# endregion


# region 修改员工状态请求
class EmployeesStatusUpdateRequest(BaseModel):
    """店长启用或停用员工时提交的状态。"""

    is_active: bool = Field(..., description="是否启用")


# endregion


# region 修改员工详情请求
class EmployeeDetailUpdateRequest(BaseModel):
    """店长提交完整的员工详情编辑表单。"""

    # 编辑详情时，除离职日期和原因外，其余六个字段必须提交且不能为 null。
    gender: EmployeeGender = Field(..., description="性别：男、女、未填写")
    # 日期只包含年月日，请求示例："2000-05-10"。
    birth_date: date = Field(..., description="出生日期")
    hire_date: date = Field(..., description="入职日期")
    phone: str = Field(..., description="联系电话", min_length=1, max_length=30)
    address: str = Field(..., description="居住地址", min_length=1, max_length=255)
    employment_status: EmploymentStatus = Field(
        ...,
        description="雇佣状态：在职、休假、离职、解雇",
    )
    # 允许暂不填写；状态变更时的日期补全及先后关系由 Service 处理。
    separation_date: date | None = Field(None, description="离职或解雇日期")
    separation_reason: str | None = Field(
        None,
        description="离职或解雇原因",
        max_length=255,
    )

    # 自动清除联系电话、地址和原因两端的空格。
    model_config = ConfigDict(str_strip_whitespace=True)


# endregion


__all__ = [
    "EmployeeDetailUpdateRequest",
    "EmployeesCreateRequest",
    "EmployeesListRequest",
    "EmployeesStatusUpdateRequest",
]
