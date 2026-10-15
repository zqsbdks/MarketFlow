"""discard_analysis：数据库读写函数。"""

from datetime import datetime, time, timedelta

from sqlalchemy import func, select

from app.models.inventory_discard import InventoryDiscard
from app.models.store import Store


async def get_loss_groups(db, request):
    """执行get_discard_analysis所需的数据库查询或更新；权限由调用它的服务检查。"""
    conditions = [
        InventoryDiscard.created_at >= datetime.combine(request.start_date, time.min),
        InventoryDiscard.created_at
        < datetime.combine(request.end_date + timedelta(days=1), time.min),
    ]
    if request.department_id is not None:
        conditions.append(InventoryDiscard.department_id == request.department_id)
    store_query_2 = select(
        func.count(InventoryDiscard.id),
        func.coalesce(func.sum(InventoryDiscard.quantity), 0),
        func.coalesce(func.sum(InventoryDiscard.total_cost), 0),
    ).where(*conditions)
    if db.info.get("read_store_id") is not None:
        store_query_2 = store_query_2.where(InventoryDiscard.store_id == db.info["read_store_id"])
    store_query_1 = (
        select(
            InventoryDiscard.store_id,
            Store.store_no,
            Store.name,
            InventoryDiscard.department_id,
            InventoryDiscard.department_name,
            InventoryDiscard.reason_code,
            func.count(InventoryDiscard.id),
            func.sum(InventoryDiscard.quantity),
            func.sum(InventoryDiscard.total_cost),
        )
        .join(Store, Store.id == InventoryDiscard.store_id)
        .where(*conditions)
        .group_by(
            InventoryDiscard.store_id,
            Store.store_no,
            Store.name,
            InventoryDiscard.department_id,
            InventoryDiscard.department_name,
            InventoryDiscard.reason_code,
        )
    )
    if db.info.get("read_store_id") is not None:
        store_query_1 = store_query_1.where(InventoryDiscard.store_id == db.info["read_store_id"])
    return await db.execute(store_query_1)


async def get_loss_totals(db, request):
    """构建并执行get_discard_analysis_execute_2的查询，店铺条件在这里明确添加。"""
    conditions = [
        InventoryDiscard.created_at >= datetime.combine(request.start_date, time.min),
        InventoryDiscard.created_at
        < datetime.combine(request.end_date + timedelta(days=1), time.min),
    ]
    if request.department_id is not None:
        conditions.append(InventoryDiscard.department_id == request.department_id)
    store_query_2 = select(
        func.count(InventoryDiscard.id),
        func.coalesce(func.sum(InventoryDiscard.quantity), 0),
        func.coalesce(func.sum(InventoryDiscard.total_cost), 0),
    ).where(*conditions)
    if db.info.get("read_store_id") is not None:
        store_query_2 = store_query_2.where(InventoryDiscard.store_id == db.info["read_store_id"])
    return await db.execute(store_query_2)
