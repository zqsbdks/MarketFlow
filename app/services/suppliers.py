"""供应商管理业务逻辑。"""

from fastapi import HTTPException
from fastapi import status as http_status
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.auth import get_employee_by_id
from app.crud.suppliers import (
    get_all_suppliers,
    get_supplier_by_id,
    get_supplier_by_name,
    put_supplier_status,
    update_supplier,
)
from app.models.enums import EmployeeRole
from app.schemas.suppliers_requests import SuppliersUpdateRequest
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


# region 修改供应商详情
async def update_supplier_service(
    supplier_id: int,
    request: SuppliersUpdateRequest,
    db: AsyncSession,
    current_employee_id: int,
) -> SupplierItemResponse:
    """验证店长权限，按需修改供应商资料并返回数据库中的最新记录。"""

    # current_employee_id来自登录令牌；先取得执行修改操作的当前员工。
    current_employee = await get_employee_by_id(employee_id=current_employee_id, db=db)
    if current_employee is None:
        raise HTTPException(
            status_code=http_status.HTTP_401_UNAUTHORIZED,
            detail="当前登录员工不存在",
            headers={"WWW-Authenticate": "Bearer"},
        )
    # 已停用账号即使令牌尚未过期，也不允许继续修改数据。
    if not current_employee.is_active:
        raise HTTPException(status_code=http_status.HTTP_403_FORBIDDEN, detail="账号已停用")
    # 使用初始密码登录的员工必须先修改密码。
    if current_employee.must_change_password:
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail="请先修改初始密码",
        )

    # 修改供应商资料属于管理操作，只允许店长执行。
    if current_employee.role != EmployeeRole.STORE_MANAGER:
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail="只有店长可以修改供应商详情",
        )

    # supplier_id来自URL；更新前先确认目标供应商确实存在。
    existing_supplier = await get_supplier_by_id(supplier_id=supplier_id, db=db)
    if existing_supplier is None:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail="供应商不存在",
        )

    # 把请求模型转为字典，并排除前端没有提交的字段，实现局部更新。
    update_data = request.model_dump(exclude_unset=True)
    if not update_data:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail="至少传入一个需要修改的字段",
        )

    # supplier_no不在请求模型中，因此创建后不能通过这个接口修改。
    # name在数据库中不允许为NULL；显式传null时提前返回友好错误。
    if update_data.get("name", existing_supplier.name) is None:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail="供应商名称不能为空",
        )

    # 只有前端提交了新名称时才查询数据库，检查名称是否被其他供应商使用。
    new_name = update_data.get("name")
    if isinstance(new_name, str):
        supplier_with_same_name = await get_supplier_by_name(
            name=new_name,
            excluded_supplier_id=supplier_id,
            db=db,
        )
        if supplier_with_same_name is not None:
            raise HTTPException(
                status_code=http_status.HTTP_409_CONFLICT,
                detail="供应商名称已被其他供应商使用",
            )

    # CRUD只执行UPDATE；Service统一负责提交当前事务。
    await update_supplier(supplier_id=supplier_id, update_data=update_data, db=db)
    await db.commit()

    # 提交后重新查询，取得数据库最新的字段以及自动更新的updated_at。
    updated_supplier = await get_supplier_by_id(supplier_id=supplier_id, db=db)
    if updated_supplier is None:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail="供应商不存在",
        )

    # 将SQLAlchemy对象转换为接口约定的Pydantic响应模型。
    return SupplierItemResponse.model_validate(updated_supplier)


# endregion

__all__ = [
    "get_supplier_detail_service",
    "get_suppliers_list_service",
    "update_supplier_service",
    "update_supplier_status_service",
]
