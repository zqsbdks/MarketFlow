"""进货管理的业务逻辑。"""

from datetime import date

from fastapi import HTTPException
from fastapi import status as http_status
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.auth import get_employee_by_id
from app.crud.purchases import get_all_purchases, get_purchase_by_id
from app.models.enums import PurchaseStatus
from app.schemas.purchases_responses import (
    PurchaseDetailResponse,
    PurchaseItemResponse,
    PurchaseListItemResponse,
    PurchaseListResponse,
)


# region 获取进货单列表
async def get_purchases_list_service(
    page: int,
    page_size: int,
    purchase_no: str | None,
    department_id: int | None,
    ordered_at: date | None,
    arrived_at: date | None,
    purchase_status: PurchaseStatus | None,
    current_employee_id: int,
    db: AsyncSession,
) -> PurchaseListResponse:
    """验证当前员工状态，并返回筛选和分页后的进货单列表。"""

    current_employee = await get_employee_by_id(employee_id=current_employee_id, db=db)
    if current_employee is None:
        raise HTTPException(
            status_code=http_status.HTTP_401_UNAUTHORIZED,
            detail="当前登录员工不存在",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not current_employee.is_active:
        raise HTTPException(status_code=http_status.HTTP_403_FORBIDDEN, detail="账号已停用")
    if current_employee.must_change_password:
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail="请先修改初始密码",
        )

    offset = (page - 1) * page_size
    purchases, total = await get_all_purchases(
        offset=offset,
        page_size=page_size,
        purchase_no=purchase_no,
        department_id=department_id,
        ordered_at=ordered_at,
        arrived_at=arrived_at,
        purchase_status=purchase_status,
        db=db,
    )

    items: list[PurchaseListItemResponse] = []
    for purchase, item_count, total_quantity in purchases:
        # 待到货进货单没有签收员工，因此签收员工姓名默认返回None。
        received_by_name = None
        if purchase.received_by_employee is not None:
            received_by_name = purchase.received_by_employee.name

        items.append(
            PurchaseListItemResponse(
                id=purchase.id,
                purchase_no=purchase.purchase_no,
                department_id=purchase.department_id,
                department_name=purchase.department.name,
                created_by=purchase.created_by,
                created_by_name=purchase.created_by_employee.name,
                received_by=purchase.received_by,
                received_by_name=received_by_name,
                ordered_at=purchase.ordered_at,
                expected_arrival_at=purchase.expected_arrival_at,
                arrived_at=purchase.arrived_at,
                total_amount=purchase.total_amount,
                status=purchase.status,
                item_count=item_count,
                total_quantity=total_quantity,
                created_at=purchase.created_at,
                updated_at=purchase.updated_at,
            )
        )

    return PurchaseListResponse(
        items=items,
        page=page,
        page_size=page_size,
        total=total,
        total_pages=(total + page_size - 1) // page_size,
    )


# endregion


# region 获取进货单详情
async def get_purchase_detail_service(
    purchase_id: int,
    current_employee_id: int,
    db: AsyncSession,
) -> PurchaseDetailResponse:
    """验证当前员工状态，并返回进货单及其全部商品明细。"""

    current_employee = await get_employee_by_id(employee_id=current_employee_id, db=db)
    if current_employee is None:
        raise HTTPException(
            status_code=http_status.HTTP_401_UNAUTHORIZED,
            detail="当前登录员工不存在",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not current_employee.is_active:
        raise HTTPException(status_code=http_status.HTTP_403_FORBIDDEN, detail="账号已停用")
    if current_employee.must_change_password:
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail="请先修改初始密码",
        )

    purchase = await get_purchase_by_id(purchase_id=purchase_id, db=db)
    if purchase is None:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="进货单不存在")

    received_by_name = None
    if purchase.received_by_employee is not None:
        received_by_name = purchase.received_by_employee.name

    # 明细里的名称使用下单快照，之后修改正式商品或供应商名称不会改变历史单据。
    detail_items: list[PurchaseItemResponse] = []
    total_quantity = 0
    for purchase_item in purchase.items:
        total_quantity += purchase_item.quantity
        detail_items.append(
            PurchaseItemResponse(
                id=purchase_item.id,
                supplier_product_id=purchase_item.supplier_product_id,
                product_id=purchase_item.product_id,
                supplier_id=purchase_item.supplier_id,
                product_no=purchase_item.product_no_snapshot,
                product_name=purchase_item.product_name_snapshot,
                supplier_name=purchase_item.supplier_name_snapshot,
                quantity=purchase_item.quantity,
                unit_cost=purchase_item.unit_cost,
                subtotal=purchase_item.subtotal,
                production_date=purchase_item.production_date,
                expiration_date=purchase_item.expiration_date,
            )
        )

    return PurchaseDetailResponse(
        id=purchase.id,
        purchase_no=purchase.purchase_no,
        department_id=purchase.department_id,
        department_name=purchase.department.name,
        created_by=purchase.created_by,
        created_by_name=purchase.created_by_employee.name,
        received_by=purchase.received_by,
        received_by_name=received_by_name,
        ordered_at=purchase.ordered_at,
        expected_arrival_at=purchase.expected_arrival_at,
        arrived_at=purchase.arrived_at,
        total_amount=purchase.total_amount,
        status=purchase.status,
        item_count=len(detail_items),
        total_quantity=total_quantity,
        created_at=purchase.created_at,
        updated_at=purchase.updated_at,
        items=detail_items,
    )


# endregion


__all__ = ["get_purchase_detail_service", "get_purchases_list_service"]
