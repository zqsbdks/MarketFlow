"""总部门店维护、统一目录维护和员工异动请求。"""

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import EmployeeRole


class StoreWriteRequest(BaseModel):
    """总部创建或修改门店的输入，编号唯一性和状态约束由服务层验证。"""

    model_config = ConfigDict(str_strip_whitespace=True)
    name: str = Field(..., min_length=1, max_length=100)
    address: str | None = Field(None, max_length=255)
    phone: str | None = Field(None, max_length=30)
    is_active: bool = True
    department_ids: list[int] = Field(default_factory=list)
    reason: str | None = Field(None, max_length=255)


class StoreDepartmentRequest(BaseModel):
    """总部启用或停用门店部门的输入，不能直接绕过引用检查。"""

    is_active: bool
    reason: str | None = Field(None, max_length=255)


class EmployeeTransferRequest(BaseModel):
    """总部员工调店、部门与角色调整输入，目标店部门需启用。"""

    store_id: int | None = Field(None, ge=1)
    department_id: int | None = Field(None, ge=1)
    role: EmployeeRole | None = None
    reason: str | None = Field(None, max_length=255)


class HeadquartersEmployeeCreateRequest(EmployeeTransferRequest):
    """总部创建员工的身份、归属和初始资料输入。"""

    name: str = Field(..., min_length=1, max_length=50)
    role: EmployeeRole


class CompanyDepartmentRequest(BaseModel):
    """全公司统一部门目录维护输入，不属于单个门店私有配置。"""

    code: str = Field(..., min_length=1, max_length=20)
    name: str = Field(..., min_length=1, max_length=50)
    is_active: bool = True


class CompanyCategoryRequest(BaseModel):
    """全公司部门内商品分类目录维护输入。"""

    department_id: int = Field(..., ge=1)
    name: str = Field(..., min_length=1, max_length=50)
    is_active: bool = True
