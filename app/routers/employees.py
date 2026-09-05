"""员工管理 API 路由。"""

from fastapi import APIRouter, Depends, Path
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies.auth import get_current_employee_id
from app.dependencies.db import get_db
from app.schemas.base import ResponseModel
from app.schemas.employees_requests import (
    EmployeeDetailUpdateRequest,
    EmployeesCreateRequest,
    EmployeesListRequest,
    EmployeesStatusUpdateRequest,
)
from app.schemas.employees_responses import (
    EmployeeDetailResponse,
    EmployeesCreateResponse,
    EmployeesListResponse,
    EmployeesResetPasswordResponse,
    EmployeesStatusUpdateResponse,
)
from app.services.employees import (
    create_employee_service,
    get_employee_detail_service,
    get_list_employees_service,
    reset_employee_password_service,
    update_employee_detail_service,
    update_employee_status_service,
)

employees_router = APIRouter(prefix="/employees", tags=["employees"])


# region 创建员工接口
@employees_router.post(
    "/create",
    response_model=ResponseModel[EmployeesCreateResponse],
    summary="创建员工",
    description="创建员工并返回员工编号、临时密码和首次修改密码标记。",
)
async def create_employee(
    employee: EmployeesCreateRequest,
    current_employee_id: int = Depends(get_current_employee_id),
    db: AsyncSession = Depends(get_db),
) -> ResponseModel[EmployeesCreateResponse]:
    """由当前登录店长创建员工账号。"""

    new_employee = await create_employee_service(
        name=employee.name,
        role=employee.role,
        department_id=employee.department_id,
        current_employee_id=current_employee_id,
        db=db,
    )

    return ResponseModel[EmployeesCreateResponse](
        message="员工创建成功",
        data=new_employee,
    )


# endregion


# region 获取员工列表接口
@employees_router.get(
    "/list",
    response_model=ResponseModel[EmployeesListResponse],
    summary="获取员工列表",
    description="获取所有员工的列表。",
)
async def get_list_employees(
    request: EmployeesListRequest = Depends(),
    current_employee_id: int = Depends(get_current_employee_id),
    db: AsyncSession = Depends(get_db),
) -> ResponseModel[EmployeesListResponse]:
    """按照分页和筛选条件返回员工列表。"""

    employees = await get_list_employees_service(
        page=request.page,
        page_size=request.page_size,
        department_id=request.department_id,
        role=request.role,
        is_active=request.is_active,
        current_employee_id=current_employee_id,
        db=db,
    )

    return ResponseModel[EmployeesListResponse](
        message="获取员工列表成功",
        data=employees,
    )


# endregion


# region 修改员工状态接口
@employees_router.put(
    "/status/{employee_id}",
    response_model=ResponseModel[EmployeesStatusUpdateResponse],
    summary="修改员工状态",
    description="店长启用或停用指定员工账号。",
)
async def update_employee_status(
    request: EmployeesStatusUpdateRequest,
    employee_id: int = Path(..., description="员工ID", ge=1),
    current_employee_id: int = Depends(get_current_employee_id),
    db: AsyncSession = Depends(get_db),
) -> ResponseModel[EmployeesStatusUpdateResponse]:
    """修改指定员工的状态。"""

    updated_employee = await update_employee_status_service(
        employee_id=employee_id,
        is_active=request.is_active,
        current_employee_id=current_employee_id,
        db=db,
    )

    return ResponseModel[EmployeesStatusUpdateResponse](
        message="员工状态更新成功",
        data=updated_employee,
    )


# endregion


# region 重置员工密码接口
@employees_router.put(
    "/reset-password/{employee_id}",
    response_model=ResponseModel[EmployeesResetPasswordResponse],
    summary="重置员工密码",
    description="店长将指定员工密码重置为临时密码。",
)
async def reset_employee_password(
    employee_id: int = Path(..., description="员工ID", ge=1),
    current_employee_id: int = Depends(get_current_employee_id),
    db: AsyncSession = Depends(get_db),
) -> ResponseModel[EmployeesResetPasswordResponse]:
    """重置指定员工密码并返回一次性临时密码。"""

    employee = await reset_employee_password_service(
        employee_id=employee_id,
        current_employee_id=current_employee_id,
        db=db,
    )

    return ResponseModel[EmployeesResetPasswordResponse](
        message="员工密码重置成功",
        data=employee,
    )


# endregion


# region 获取员工详情接口
@employees_router.get(
    "/{employee_id}",
    response_model=ResponseModel[EmployeeDetailResponse],
    summary="获取员工详情",
    description="员工可以查看本人详情，店长可以查看所有员工详情。",
)
async def get_employee_detail(
    employee_id: int = Path(..., description="员工ID", ge=1),
    current_employee_id: int = Depends(get_current_employee_id),
    db: AsyncSession = Depends(get_db),
) -> ResponseModel[EmployeeDetailResponse]:
    """接收目标员工 ID，并返回统一格式的员工详情。"""

    # employee_id 来自 URL；current_employee_id 来自当前登录 Token。
    # Service 负责权限检查，返回已组装好的 EmployeeDetailResponse 对象。
    detail = await get_employee_detail_service(
        employee_id=employee_id,
        current_employee_id=current_employee_id,
        db=db,
    )

    return ResponseModel[EmployeeDetailResponse](
        # data 中仅包含响应模型定义的公开字段，不包含密码哈希。
        message="员工详情获取成功",
        data=detail,
    )


# endregion


# region 修改员工详情接口
@employees_router.put(
    "/{employee_id}",
    response_model=ResponseModel[EmployeeDetailResponse],
    summary="修改员工详情",
    description="店长提交完整资料，修改指定员工详情。",
)
async def update_employee_detail(
    request: EmployeeDetailUpdateRequest,
    employee_id: int = Path(..., description="员工ID", ge=1),
    current_employee_id: int = Depends(get_current_employee_id),
    db: AsyncSession = Depends(get_db),
) -> ResponseModel[EmployeeDetailResponse]:
    """从 JSON 请求体接收详情，返回保存后的员工资料。"""

    # URL 指定被修改的员工；Token 指定操作人，两者不能混用。
    update_detail = await update_employee_detail_service(
        employee_id=employee_id,
        request=request,
        current_employee_id=current_employee_id,
        db=db,
    )

    return ResponseModel[EmployeeDetailResponse](
        message="员工详情修改成功",
        data=update_detail,
    )


# endregion

__all__ = ["employees_router"]
