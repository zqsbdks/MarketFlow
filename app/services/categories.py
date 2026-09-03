"""商品分类查询业务逻辑。"""

from fastapi import HTTPException
from fastapi import status as http_status
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.auth import get_employee_by_id
from app.crud.categories import get_categories_list
from app.schemas.categories_responses import CategoriesItemResponse


# region 获取商品分类列表
async def get_categories_list_service(
    department_id: int | None,
    current_employee_id: int,
    db: AsyncSession,
) -> list[CategoriesItemResponse]:
    """验证当前员工账号，并返回经过部门筛选的分类列表。"""

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

    categories = await get_categories_list(
        department_id=department_id,
        db=db,
    )

    # 分步组装响应列表，便于查看每个分类字段的来源。
    category_items: list[CategoriesItemResponse] = []
    for category in categories:
        category_item = CategoriesItemResponse(
            id=category.id,
            name=category.name,
            department_id=category.department_id,
        )
        category_items.append(category_item)

    return category_items


# endregion


__all__ = ["get_categories_list_service"]
