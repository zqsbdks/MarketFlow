"""统一操作审计记录数据访问函数。"""

from datetime import datetime
from typing import Any

from fastapi.encoders import jsonable_encoder
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from app.models.employee import Employee
from app.models.inventory_batch import InventoryBatch
from app.models.operation_audit_log import OperationAuditLog
from app.models.product import Product

# 状态自动刷新不改变库存数量，因此不属于库存流水。
INVENTORY_MOVEMENT_ACTIONS = (
    "create_batch",
    "sale_deduction",
    "update_quantity",
    "discard_expired",
)


# region 创建操作审计记录
async def create_operation_audit_log(
    *,
    employee_id: int | None,
    module: str,
    action: str,
    target_type: str,
    target_id: int,
    before_data: dict[str, Any] | None,
    after_data: dict[str, Any] | None,
    reason: str | None,
    db: AsyncSession,
) -> OperationAuditLog:
    """把一次数据变更加入当前事务；系统自动任务的员工 ID 可以为空。"""

    log = OperationAuditLog(
        employee_id=employee_id,
        module=module,
        action=action,
        target_type=target_type,
        target_id=target_id,
        before_data=jsonable_encoder(before_data),
        after_data=jsonable_encoder(after_data),
        reason=reason,
    )
    db.add(log)
    await db.flush()
    return log


# endregion


# region 获取库存变动流水
async def get_inventory_movements(
    offset: int,
    page_size: int,
    keyword: str | None,
    action: str | None,
    batch_id: int | None,
    product_id: int | None,
    start_time: datetime | None,
    end_time: datetime | None,
    db: AsyncSession,
) -> tuple[
    list[tuple[OperationAuditLog, str | None, str | None, int | None, str | None, str | None]],
    int,
]:
    """查询改变批次数量的审计记录，并关联员工、批次和商品。"""

    conditions: list[ColumnElement[bool]] = [
        OperationAuditLog.module == "inventory",
        OperationAuditLog.target_type == "inventory_batch",
        OperationAuditLog.action.in_(INVENTORY_MOVEMENT_ACTIONS),
    ]
    if keyword is not None:
        fuzzy_keyword = f"%{keyword}%"
        conditions.append(
            or_(
                InventoryBatch.batch_no.ilike(fuzzy_keyword),
                Product.product_no.ilike(fuzzy_keyword),
                Product.name.ilike(fuzzy_keyword),
            )
        )
    if action is not None:
        conditions.append(OperationAuditLog.action == action)
    if batch_id is not None:
        conditions.append(OperationAuditLog.target_id == batch_id)
    if product_id is not None:
        conditions.append(InventoryBatch.product_id == product_id)
    if start_time is not None:
        conditions.append(OperationAuditLog.created_at >= start_time)
    if end_time is not None:
        conditions.append(OperationAuditLog.created_at <= end_time)

    # 使用左连接，即使员工为系统任务，流水也不会丢失。
    base_statement = (
        select(
            OperationAuditLog,
            Employee.name,
            InventoryBatch.batch_no,
            Product.id,
            Product.product_no,
            Product.name,
        )
        .outerjoin(Employee, Employee.id == OperationAuditLog.employee_id)
        .outerjoin(InventoryBatch, InventoryBatch.id == OperationAuditLog.target_id)
        .outerjoin(Product, Product.id == InventoryBatch.product_id)
        .where(*conditions)
    )
    list_statement = (
        base_statement.order_by(OperationAuditLog.created_at.desc(), OperationAuditLog.id.desc())
        .offset(offset)
        .limit(page_size)
    )
    count_statement = (
        select(func.count(OperationAuditLog.id))
        .outerjoin(InventoryBatch, InventoryBatch.id == OperationAuditLog.target_id)
        .outerjoin(Product, Product.id == InventoryBatch.product_id)
        .where(*conditions)
    )

    total = int(await db.scalar(count_statement) or 0)
    rows = (await db.execute(list_statement)).all()
    return [
        (audit_log, employee_name, batch_no, joined_product_id, product_no, product_name)
        for (
            audit_log,
            employee_name,
            batch_no,
            joined_product_id,
            product_no,
            product_name,
        ) in rows
    ], total


# endregion


# region 获取操作审计记录
async def get_operation_audit_logs(
    offset: int,
    page_size: int,
    employee_id: int | None,
    module: str | None,
    action: str | None,
    target_type: str | None,
    target_id: int | None,
    start_time: datetime | None,
    end_time: datetime | None,
    db: AsyncSession,
) -> tuple[list[tuple[OperationAuditLog, str | None]], int]:
    """分页查询审计记录，并同时返回操作员工姓名和符合条件的总数。"""

    # 只把前端实际传入的筛选项加入查询；空条件列表表示查询全部审计记录。
    conditions: list[ColumnElement[bool]] = []
    if employee_id is not None:
        conditions.append(OperationAuditLog.employee_id == employee_id)
    if module is not None:
        conditions.append(OperationAuditLog.module == module)
    if action is not None:
        conditions.append(OperationAuditLog.action == action)
    if target_type is not None:
        conditions.append(OperationAuditLog.target_type == target_type)
    if target_id is not None:
        conditions.append(OperationAuditLog.target_id == target_id)
    if start_time is not None:
        conditions.append(OperationAuditLog.created_at >= start_time)
    if end_time is not None:
        conditions.append(OperationAuditLog.created_at <= end_time)

    # employee_id 允许为空，因此使用左连接；系统自动任务也会保留在查询结果中。
    list_statement = (
        select(OperationAuditLog, Employee.name)
        .outerjoin(Employee, Employee.id == OperationAuditLog.employee_id)
        .where(*conditions)
        .order_by(OperationAuditLog.created_at.desc(), OperationAuditLog.id.desc())
        .offset(offset)
        .limit(page_size)
    )
    count_statement = select(func.count(OperationAuditLog.id)).where(*conditions)

    total = int(await db.scalar(count_statement) or 0)
    rows = (await db.execute(list_statement)).all()
    return [(audit_log, employee_name) for audit_log, employee_name in rows], total


# endregion

__all__ = [
    "create_operation_audit_log",
    "get_inventory_movements",
    "get_operation_audit_logs",
]
