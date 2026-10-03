"""总部门店维护、统一目录维护和员工异动请求。"""

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import EmployeeRole


class StoreWriteRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    name: str = Field(..., min_length=1, max_length=100)
    address: str | None = Field(None, max_length=255)
    phone: str | None = Field(None, max_length=30)
    is_active: bool = True
    department_ids: list[int] = Field(default_factory=list)
    reason: str | None = Field(None, max_length=255)


class StoreDepartmentRequest(BaseModel):
    is_active: bool
    reason: str | None = Field(None, max_length=255)


class EmployeeTransferRequest(BaseModel):
    store_id: int | None = Field(None, ge=1)
    department_id: int | None = Field(None, ge=1)
    role: EmployeeRole | None = None
    reason: str | None = Field(None, max_length=255)


class HeadquartersEmployeeCreateRequest(EmployeeTransferRequest):
    name: str = Field(..., min_length=1, max_length=50)
    role: EmployeeRole


class CompanyDepartmentRequest(BaseModel):
    code: str = Field(..., min_length=1, max_length=20)
    name: str = Field(..., min_length=1, max_length=50)
    is_active: bool = True


class CompanyCategoryRequest(BaseModel):
    department_id: int = Field(..., ge=1)
    name: str = Field(..., min_length=1, max_length=50)
    is_active: bool = True
