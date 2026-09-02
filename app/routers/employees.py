"""员工管理 API 路由。"""

from fastapi import APIRouter, Depends, Path
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies.auth import get_current_employee_id
from app.dependencies.db import get_db
from app.schemas.base import ResponseModel
from app.schemas.employees_requests import (
    EmployeesCreateRequest,
    EmployeesListRequest,
    EmployeesStatusUpdateRequest,
)
from app.schemas.employees_responses import (
    EmployeesCreateResponse,
    EmployeesListResponse,
    EmployeesStatusUpdateResponse,
)
from app.services.employees import (
    create_employee_service,
    get_list_employees_service,
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


__all__ = ["employees_router"]
