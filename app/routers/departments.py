"""部门查询 API 路由。"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies.auth import get_current_employee_id
from app.dependencies.db import get_db
from app.schemas.base import ResponseModel
from app.schemas.departments_responses import DepartmentItemResponse
from app.services.departments import get_departments_list_service

departments_router = APIRouter(
    prefix="/departments",
    tags=["departments"],
)


# region 获取部门列表接口
@departments_router.get(
    "",
    response_model=ResponseModel[list[DepartmentItemResponse]],
    summary="获取部门列表",
    description="返回所有部门的列表。",
)
async def get_departments_list(
    current_employee_id: int = Depends(get_current_employee_id),
    db: AsyncSession = Depends(get_db),
) -> ResponseModel[list[DepartmentItemResponse]]:
    """获取部门列表，并使用项目统一响应格式返回。"""

    departments = await get_departments_list_service(
        current_employee_id=current_employee_id,
        db=db,
    )

    return ResponseModel[list[DepartmentItemResponse]](
        message="获取部门列表成功",
        data=departments,
    )


# endregion


__all__ = ["departments_router"]
