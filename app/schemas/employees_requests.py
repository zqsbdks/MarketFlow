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


__all__ = ["EmployeesCreateRequest"]
