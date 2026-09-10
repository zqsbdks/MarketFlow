"""供应商管理业务逻辑。"""

from fastapi import HTTPException
from fastapi import status as http_status
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.auth import get_employee_by_id
from app.crud.suppliers import get_all_suppliers, get_supplier_by_id, put_supplier_status
from app.models.enums import EmployeeRole
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

    # 根据Token中的员工ID读取当前操作人，并验证账号能否继续使用系统。
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

    # 将每个Supplier ORM对象转换成接口响应项。
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


# region 获取供应商详情
async def get_supplier_detail_service(
    supplier_id: int,
    current_employee_id: int,
    db: AsyncSession,
) -> SupplierItemResponse:
    """验证当前员工状态，并返回指定供应商的完整基础资料。"""

    # 根据Token中的员工ID读取当前操作人，并验证账号能否查看供应商资料。
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

    # supplier_id来自URL；查询不到时返回明确的404，而不是返回空data。
    supplier = await get_supplier_by_id(supplier_id=supplier_id, db=db)
    if supplier is None:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail="供应商不存在",
        )

    return SupplierItemResponse.model_validate(supplier)


# endregion


# region 修改供应商状态
async def update_supplier_status_service(
    supplier_id: int,
    is_active: bool,
    current_employee_id: int,
    db: AsyncSession,
) -> SupplierItemResponse:
    """验证店长权限，修改供应商合作状态并返回数据库中的最新资料。"""

    # 修改状态属于管理操作，因此除了账号状态外还要验证店长角色。
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
    if employee.role != EmployeeRole.STORE_MANAGER:
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail="只有店长可以修改供应商状态",
        )

    # 更新前先确认目标存在，否则UPDATE零行也无法区分“未找到”和“修改成功”。
    supplier = await get_supplier_by_id(supplier_id=supplier_id, db=db)
    if supplier is None:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail="供应商不存在",
        )

    # CRUD只执行UPDATE，事务由Service统一提交。
    await put_supplier_status(supplier_id=supplier_id, is_active=is_active, db=db)
    await db.commit()

    # 重新查询可以取得最新is_active和数据库自动更新的updated_at。
    updated_supplier = await get_supplier_by_id(supplier_id=supplier_id, db=db)
    if updated_supplier is None:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail="供应商不存在",
        )

    return SupplierItemResponse.model_validate(updated_supplier)


# endregion

__all__ = [
    "get_supplier_detail_service",
    "get_suppliers_list_service",
    "update_supplier_status_service",
]
