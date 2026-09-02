"""员工管理接口的请求模型。"""

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import EmployeeRole


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


__all__ = [
    "EmployeesCreateRequest",
    "EmployeesListRequest",
    "EmployeesStatusUpdateRequest",
]
