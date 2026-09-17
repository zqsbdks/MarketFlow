"""库存批次业务逻辑。"""

from fastapi import HTTPException
from fastapi import status as http_status
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.auth import get_employee_by_id
from app.crud.inventory_batches import get_inventory_batch_by_id, get_inventory_batches_list
from app.models.enums import InventoryBatchStatus
from app.schemas.inventory_batches_responses import (
    InventoryBatchDetailResponse,
    InventoryBatchItemResponse,
    InventoryBatchListResponse,
)


# region 获取库存批次列表
async def get_inventory_batches_list_service(
    # page：前端指定的当前页码。
    page: int,
    # page_size：前端指定的每页数量。
    page_size: int,
    # status：可选批次状态筛选条件。
    status: InventoryBatchStatus | None,
    # current_employee_id：当前登录员工 ID，用于检查账号有效性。
    current_employee_id: int,
    # db：当前请求使用的异步数据库会话。
    db: AsyncSession,
) -> InventoryBatchListResponse:
    """验证当前账号有效，并组装全部部门的分页库存批次列表。"""

    # 第一步：查询当前登录员工并检查账号的最新状态。
    current_employee = await get_employee_by_id(
        employee_id=current_employee_id,
        db=db,
    )
    if current_employee is None:
        raise HTTPException(
            status_code=http_status.HTTP_401_UNAUTHORIZED,
            detail="当前登录员工不存在",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 员工账号已被停用时，即使旧令牌尚未过期也不能继续查询。
    if not current_employee.is_active:
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail="当前账号已停用",
        )

    # 使用初始密码的员工需要先完成首次密码修改。
    if current_employee.must_change_password:
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail="请先修改初始密码",
        )

    # 第二步：获取当前页批次以及符合筛选条件的总记录数。
    # 所有有效员工都查询全部部门，不按照角色或所属部门过滤。
    batches, total = await get_inventory_batches_list(
        page=page,
        page_size=page_size,
        status=status,
        db=db,
    )

    # 第三步：把批次、商品和部门数据组装成前端需要的平铺列表项。
    items: list[InventoryBatchItemResponse] = []
    for batch in batches:
        item = InventoryBatchItemResponse(
            id=batch.id,
            batch_no=batch.batch_no,
            product_no=batch.product.product_no,
            product_name=batch.product.name,
            department_name=batch.product.department.name,
            initial_quantity=batch.initial_quantity,
            remaining_quantity=batch.remaining_quantity,
            production_date=batch.production_date,
            expiration_date=batch.expiration_date,
            status=batch.status,
            arrived_at=batch.arrived_at,
        )
        items.append(item)

    # 第四步：向上取整计算总页数；没有记录时结果为 0。
    total_pages = (total + page_size - 1) // page_size

    return InventoryBatchListResponse(
        items=items,
        page=page,
        page_size=page_size,
        total=total,
        total_pages=total_pages,
    )


# endregion


# region 获取库存批次详情
async def get_inventory_batch_detail_service(
    # batch_id：准备查看的库存批次 ID。
    batch_id: int,
    # current_employee_id：当前登录员工 ID，用于检查账号有效性。
    current_employee_id: int,
    # db：当前请求使用的异步数据库会话。
    db: AsyncSession,
) -> InventoryBatchDetailResponse:
    """验证当前账号有效，并返回指定库存批次的完整详情。"""

    # 第一步：检查当前员工存在、账号启用并且已经修改初始密码。
    # 所有员工角色均可查看，不进行角色和所属部门限制。
    current_employee = await get_employee_by_id(
        employee_id=current_employee_id,
        db=db,
    )
    if current_employee is None:
        raise HTTPException(
            status_code=http_status.HTTP_401_UNAUTHORIZED,
            detail="当前登录员工不存在",
            headers={"WWW-Authenticate": "Bearer"},
        )
    # 停用账号不能继续访问库存批次数据。
    if not current_employee.is_active:
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail="当前账号已停用",
        )
    # 使用初始密码的员工需要先完成首次密码修改。
    if current_employee.must_change_password:
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail="请先修改初始密码",
        )

    # 第二步：查询批次以及商品、部门、分类、进货明细和进货单关系。
    batch = await get_inventory_batch_by_id(batch_id=batch_id, db=db)
    if batch is None:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail="库存批次不存在",
        )

    # 第三步：把多个关联表中的字段组装成平铺的详情响应。
    return InventoryBatchDetailResponse(
        id=batch.id,
        batch_no=batch.batch_no,
        product_id=batch.product_id,
        product_no=batch.product.product_no,
        product_name=batch.product.name,
        department_id=batch.product.department_id,
        department_name=batch.product.department.name,
        category_id=batch.product.category_id,
        category_name=batch.product.category.name,
        supplier_name=batch.purchase_item.supplier_name_snapshot,
        purchase_no=batch.purchase_item.purchase.purchase_no,
        purchase_item_id=batch.purchase_item_id,
        unit_cost=batch.purchase_item.unit_cost,
        initial_quantity=batch.initial_quantity,
        remaining_quantity=batch.remaining_quantity,
        production_date=batch.production_date,
        expiration_date=batch.expiration_date,
        status=batch.status,
        arrived_at=batch.arrived_at,
        created_at=batch.created_at,
        updated_at=batch.updated_at,
    )


# endregion


__all__ = [
    "get_inventory_batch_detail_service",
    "get_inventory_batches_list_service",
]
