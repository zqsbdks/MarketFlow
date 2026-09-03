"""部门查询业务逻辑。"""

from fastapi import HTTPException
from fastapi import status as http_status
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.auth import get_employee_by_id
from app.crud.departments import get_departments_list
from app.schemas.departments_responses import DepartmentItemResponse


# region 获取部门列表
async def get_departments_list_service(
    current_employee_id: int,
    db: AsyncSession,
) -> list[DepartmentItemResponse]:
    """验证当前员工账号，并返回部门列表。"""

    # Token 签发后员工可能被删除或停用，因此请求时重新检查账号状态。
    employee = await get_employee_by_id(
        employee_id=current_employee_id,
        db=db,
    )
    if employee is None:
        raise HTTPException(
            status_code=http_status.HTTP_401_UNAUTHORIZED,
            detail="当前登录员工不存在",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not employee.is_active:
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail="账号已停用",
        )

    if employee.must_change_password:
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail="请先修改初始密码",
        )

    departments = await get_departments_list(db=db)

    # 只公开接口文档要求的部门 ID 和名称。
    return [
        DepartmentItemResponse(
            id=department.id,
            name=department.name,
        )
        for department in departments
    ]


# endregion


__all__ = ["get_departments_list_service"]
