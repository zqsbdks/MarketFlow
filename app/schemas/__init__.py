"""Pydantic 请求与响应模型包。

业务 Schema 可按领域拆分为独立文件；跨模块常用的类型可以在这里统一重导出。
"""

from app.schemas.auth_requests import AuthLoginRequest, AuthPasswordChangeRequest
from app.schemas.auth_responses import (
    AuthDepartmentResponse,
    AuthLoginEmployee,
    AuthLoginResponse,
    AuthMeResponse,
)
from app.schemas.base import ResponseModel
from app.schemas.employees_requests import (
    EmployeesCreateRequest,
    EmployeesListRequest,
    EmployeesStatusUpdateRequest,
)
from app.schemas.employees_responses import (
    EmployeesCreateResponse,
    EmployeesItemResponse,
    EmployeesListResponse,
    EmployeesResetPasswordResponse,
    EmployeesStatusUpdateResponse,
)
from app.schemas.products_requests import ProductsListRequest
from app.schemas.products_responses import (
    CategoryResponse,
    DepartmentResponse,
    ItemResponse,
    ProductsItemResponse,
    ProductsListResponse,
)

__all__ = [
    "AuthDepartmentResponse",
    "AuthLoginEmployee",
    "AuthLoginRequest",
    "AuthLoginResponse",
    "AuthMeResponse",
    "AuthPasswordChangeRequest",
    "CategoryResponse",
    "DepartmentResponse",
    "EmployeesCreateRequest",
    "EmployeesCreateResponse",
    "EmployeesItemResponse",
    "EmployeesListRequest",
    "EmployeesListResponse",
    "EmployeesResetPasswordResponse",
    "EmployeesStatusUpdateRequest",
    "EmployeesStatusUpdateResponse",
    "ItemResponse",
    "ProductsItemResponse",
    "ProductsListRequest",
    "ProductsListResponse",
    "ResponseModel",
]
