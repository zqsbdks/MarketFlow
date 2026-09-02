"""员工管理 API 路由。"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies.auth import get_current_employee_id
from app.dependencies.db import get_db
from app.schemas.base import ResponseModel
from app.schemas.employees_requests import EmployeesCreateRequest
from app.schemas.employees_responses import EmployeesCreateResponse
from app.services.employees import create_employee_service

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


__all__ = ["employees_router"]
