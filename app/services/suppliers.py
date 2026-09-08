"""供应商管理业务逻辑。"""

from fastapi import HTTPException
from fastapi import status as http_status
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.auth import get_employee_by_id
from app.crud.suppliers import get_all_suppliers
from app.schemas.suppliers_responses import SupplierItemResponse, SupplierListResponse


# region 获取供应商列表
async def get_suppliers_list_service(
    page: int,
    page_size: int,
    is_active: bool | None,
    current_employee_id: int,
    db: AsyncSession,
) -> SupplierListResponse:
    """返回经过状态筛选和分页的供应商列表。"""

    # 根据Token中的员工ID读取当前操作人，避免失效账号继续访问管理功能。
    employee = await get_employee_by_id(employee_id=current_employee_id, db=db)
    if employee is None:
        raise HTTPException(
            status_code=http_status.HTTP_401_UNAUTHORIZED,
            detail="当前登录员工不存在",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not employee.is_active:
        raise HTTPException(status_code=http_status.HTTP_403_FORBIDDEN, detail="账号已停用")
    if employee.must_change_password:
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail="请先修改初始密码",
        )

    # offset表示当前页之前需要跳过多少条记录，例如第2页跳过page_size条。
    offset = (page - 1) * page_size
    suppliers, total = await get_all_suppliers(
        offset=offset,
        page_size=page_size,
        is_active=is_active,
        db=db,
    )

    # 将数据库ORM对象逐个转换成接口响应项。
    items: list[SupplierItemResponse] = []
    for supplier in suppliers:
        item = SupplierItemResponse.model_validate(supplier)
        items.append(item)

    # 整数公式用于向上取整；没有供应商时总页数为0。
    total_pages = (total + page_size - 1) // page_size
    return SupplierListResponse(
        items=items,
        page=page,
        page_size=page_size,
        total=total,
        total_pages=total_pages,
    )


# endregion

__all__ = ["get_suppliers_list_service"]
