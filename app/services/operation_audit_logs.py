"""操作审计记录查询业务逻辑。"""

from datetime import datetime

from fastapi import HTTPException
from fastapi import status as http_status
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.auth import get_employee_by_id
from app.crud.operation_audit_logs import get_inventory_movements, get_operation_audit_logs
from app.models.enums import EmployeeRole
from app.schemas.operation_audit_logs_responses import (
    InventoryMovementItemResponse,
    InventoryMovementListResponse,
    OperationAuditLogItemResponse,
    OperationAuditLogListResponse,
)

INVENTORY_ACTION_NAMES = {
    "create_batch": "进货入库",
    "sale_deduction": "销售出库",
    "update_quantity": "人工盘点",
    "discard_expired": "过期废弃",
}


def _get_quantity(data: dict[str, object] | None) -> int | None:
    """从审计 JSON 中安全读取批次剩余数量。"""

    if data is None:
        return None
    quantity = data.get("remaining_quantity")
    # bool 是 int 的子类，但不是合法库存数量，因此单独排除。
    if isinstance(quantity, bool) or not isinstance(quantity, int):
        return None
    return quantity


# region 获取操作审计记录列表
async def get_operation_audit_logs_service(
    page: int,
    page_size: int,
    employee_id: int | None,
    module: str | None,
    action: str | None,
    target_type: str | None,
    target_id: int | None,
    start_time: datetime | None,
    end_time: datetime | None,
    current_employee_id: int,
    db: AsyncSession,
) -> OperationAuditLogListResponse:
    """验证店长权限和时间范围，并组装分页审计记录列表。"""

    # 审计数据包含员工操作和修改前后内容，只允许账号状态正常的店长查看。
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
    if current_employee.role != EmployeeRole.STORE_MANAGER:
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail="只有店长可以查看操作审计记录",
        )

    if start_time is not None and end_time is not None and start_time > end_time:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail="开始时间不能晚于结束时间",
        )

    offset = (page - 1) * page_size
    audit_logs, total = await get_operation_audit_logs(
        offset=offset,
        page_size=page_size,
        employee_id=employee_id,
        module=module,
        action=action,
        target_type=target_type,
        target_id=target_id,
        start_time=start_time,
        end_time=end_time,
        db=db,
    )

    # employee_id 为空的记录来自定时任务，使用明确名称方便前端直接显示。
    items: list[OperationAuditLogItemResponse] = []
    for audit_log, employee_name in audit_logs:
        items.append(
            OperationAuditLogItemResponse(
                id=audit_log.id,
                employee_id=audit_log.employee_id,
                employee_name=employee_name or "系统自动任务",
                module=audit_log.module,
                action=audit_log.action,
                target_type=audit_log.target_type,
                target_id=audit_log.target_id,
                before_data=audit_log.before_data,
                after_data=audit_log.after_data,
                reason=audit_log.reason,
                created_at=audit_log.created_at,
            )
        )

    return OperationAuditLogListResponse(
        items=items,
        page=page,
        page_size=page_size,
        total=total,
        total_pages=(total + page_size - 1) // page_size,
    )


# endregion


# region 获取库存变动流水
async def get_inventory_movements_service(
    page: int,
    page_size: int,
    keyword: str | None,
    action: str | None,
    batch_id: int | None,
    product_id: int | None,
    start_time: datetime | None,
    end_time: datetime | None,
    current_employee_id: int,
    db: AsyncSession,
) -> InventoryMovementListResponse:
    """验证店长权限，并将审计 JSON 组装成易读的库存流水。"""

    # 库存流水包含成本、销售和盘点信息，权限与通用审计记录保持一致。
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
    if current_employee.role != EmployeeRole.STORE_MANAGER:
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail="只有店长可以查看库存变动流水",
        )
    if start_time is not None and end_time is not None and start_time > end_time:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail="开始时间不能晚于结束时间",
        )

    rows, total = await get_inventory_movements(
        offset=(page - 1) * page_size,
        page_size=page_size,
        keyword=keyword,
        action=action,
        batch_id=batch_id,
        product_id=product_id,
        start_time=start_time,
        end_time=end_time,
        db=db,
    )

    items: list[InventoryMovementItemResponse] = []
    for audit_log, employee_name, batch_no, joined_product_id, product_no, product_name in rows:
        before_quantity = _get_quantity(audit_log.before_data)
        after_quantity = _get_quantity(audit_log.after_data)

        # 创建批次之前数量视为 0，才能在页面正确显示“+30”之类入库量。
        if audit_log.action == "create_batch" and before_quantity is None:
            before_quantity = 0
        change_quantity = None
        if before_quantity is not None and after_quantity is not None:
            change_quantity = after_quantity - before_quantity

        items.append(
            InventoryMovementItemResponse(
                id=audit_log.id,
                batch_id=audit_log.target_id,
                batch_no=batch_no,
                product_id=joined_product_id,
                product_no=product_no,
                product_name=product_name,
                employee_id=audit_log.employee_id,
                employee_name=employee_name or "系统自动任务",
                action=audit_log.action,
                action_name=INVENTORY_ACTION_NAMES.get(audit_log.action, audit_log.action),
                before_quantity=before_quantity,
                change_quantity=change_quantity,
                after_quantity=after_quantity,
                reason=audit_log.reason,
                created_at=audit_log.created_at,
            )
        )

    return InventoryMovementListResponse(
        items=items,
        page=page,
        page_size=page_size,
        total=total,
        total_pages=(total + page_size - 1) // page_size,
    )


# endregion


__all__ = ["get_inventory_movements_service", "get_operation_audit_logs_service"]
