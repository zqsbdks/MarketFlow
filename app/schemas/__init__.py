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
from app.schemas.categories_requests import CategoryListRequest
from app.schemas.categories_responses import CategoriesItemResponse
from app.schemas.departments_responses import DepartmentItemResponse
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
from app.schemas.reports_requests import ReportRequest
from app.schemas.reports_responses import ReportResponse
from app.schemas.sales_requests import SalesListRequest
from app.schemas.sales_responses import (
    SaleDetailItemResponse,
    SaleDetailResponse,
    SalesItemResponse,
    SalesListResponse,
)

__all__ = [
    "AuthDepartmentResponse",
    "AuthLoginEmployee",
    "AuthLoginRequest",
    "AuthLoginResponse",
    "AuthMeResponse",
    "AuthPasswordChangeRequest",
    "CategoriesItemResponse",
    "CategoryListRequest",
    "CategoryResponse",
    "DepartmentResponse",
    "DepartmentItemResponse",
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
    "ReportRequest",
    "ReportResponse",
    "SaleDetailItemResponse",
    "SaleDetailResponse",
    "SalesItemResponse",
    "SalesListRequest",
    "SalesListResponse",
]
