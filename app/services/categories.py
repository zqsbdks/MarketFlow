"""商品分类查询业务逻辑。"""

from fastapi import HTTPException, Request
from fastapi import status as http_status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import (
    CATEGORIES_CACHE_NAMESPACE,
    CATEGORIES_CACHE_SECONDS,
    business_cache,
)
from app.crud.auth import get_employee_by_id
from app.crud.categories import get_categories_list
from app.crud.stores import first_active_store_id, get_store_by_id
from app.models.enums import EmployeeRole
from app.schemas.categories_responses import CategoriesItemResponse


# region 获取商品分类列表
async def get_categories_list_service(
    department_id: int | None,
    current_employee_id: int,
    db: AsyncSession,
    *,
    http_request: Request | None = None,
) -> list[CategoriesItemResponse]:
    """验证当前员工账号，并返回经过部门筛选的分类列表。"""

    # 本接口在服务层明确检查店铺范围；不依赖数据库自动事件。
    if http_request is not None:
        access_employee = await get_employee_by_id(employee_id=current_employee_id, db=db)
        if access_employee is None or not access_employee.is_active:
            raise HTTPException(401, "账号不存在或已停用")
        is_headquarters = access_employee.role == EmployeeRole.HEADQUARTERS
        selected_store_id = access_employee.store_id
        raw_store_id = http_request.headers.get("X-Store-ID")
        if not raw_store_id:
            raw_store_id = http_request.query_params.get("store_id")
        if raw_store_id == "all":
            raise HTTPException(403, "此接口不支持全公司汇总")
        elif raw_store_id:
            try:
                selected_store_id = int(raw_store_id)
            except ValueError as error:
                raise HTTPException(422, "门店ID无效") from error
            if selected_store_id <= 0:
                raise HTTPException(422, "门店ID无效")
        if selected_store_id is None and is_headquarters and raw_store_id != "all":
            selected_store_id = await first_active_store_id(db)
        if selected_store_id is not None:
            selected_store = await get_store_by_id(selected_store_id, db)
            if selected_store is None or not selected_store.is_active:
                raise HTTPException(403, "门店不存在或已停用")
        if not is_headquarters and access_employee.store_id is None:
            raise HTTPException(403, "员工尚未分配门店")

        # 这里只记录本次查询参数；CRUD 会明确读取并添加 store_id 条件。
        db.info.update(
            actor_id=access_employee.id,
            actor_role=access_employee.role,
            own_store_id=access_employee.store_id,
            read_store_id=selected_store_id,
            write_store_id=access_employee.store_id,
            company_management=False,
            company_catalog_read=False,
            private_employee_path=False,
            store_context=True,
        )
        http_request.state.store_id = selected_store_id
        http_request.state.employee_id = access_employee.id
        http_request.state.own_store_id = access_employee.store_id

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

    return await _cached_get_categories_list_service(
        department_id=department_id, current_employee_id=current_employee_id, db=db
    )


# endregion


__all__ = ["get_categories_list_service"]


@business_cache(expire=CATEGORIES_CACHE_SECONDS, namespace=CATEGORIES_CACHE_NAMESPACE)
async def _cached_get_categories_list_service(
    department_id: int | None, current_employee_id: int, db: AsyncSession
) -> list[CategoriesItemResponse]:
    categories = await get_categories_list(department_id=department_id, db=db)
    category_items: list[CategoriesItemResponse] = []
    for category in categories:
        category_item = CategoriesItemResponse(
            id=category.id, name=category.name, department_id=category.department_id
        )
        category_items.append(category_item)
    return category_items
