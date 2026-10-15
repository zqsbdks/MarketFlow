"""inventory_discards：数据库读写函数。"""

from datetime import datetime, time, timedelta

from sqlalchemy import func, or_, select
from sqlalchemy.orm import lazyload, selectinload

from app.models.enums import EmployeeRole
from app.models.inventory_batch import InventoryBatch
from app.models.inventory_discard import InventoryDiscard, InventoryDiscardItem
from app.models.product import Product
from app.models.store import StoreDepartment


async def get_discard_product(db, lock, product_id):
    """构建并执行load_product_query的查询，店铺条件在这里明确添加。"""
    statement = (
        select(Product).where(Product.id == product_id).options(selectinload(Product.department))
    )
    if db.info.get("read_store_id") is not None:
        statement = statement.where(Product.store_id == db.info["read_store_id"])
    if lock:
        statement = statement.with_for_update().execution_options(populate_existing=True)
    return await db.scalar(statement)


async def get_product_department_enabled(db, product):
    """执行load_product所需的数据库查询；权限由调用它的服务检查。"""
    return await db.scalar(
        select(StoreDepartment.is_active).where(
            StoreDepartment.store_id == product.store_id,
            StoreDepartment.department_id == product.department_id,
        )
    )


async def get_discard_batches(db, lock, now, product):
    """构建并执行eligible_batches_query的查询，店铺条件在这里明确添加。"""
    statement = (
        select(InventoryBatch)
        .where(
            InventoryBatch.store_id == product.store_id,
            InventoryBatch.product_id == product.id,
            InventoryBatch.remaining_quantity > 0,
            InventoryBatch.arrived_at <= now,
            or_(
                InventoryBatch.expiration_date.is_(None),
                InventoryBatch.expiration_date >= now.date(),
            ),
        )
        .options(selectinload(InventoryBatch.purchase_item))
        .order_by(
            InventoryBatch.expiration_date.is_(None),
            InventoryBatch.expiration_date,
            InventoryBatch.arrived_at,
            InventoryBatch.id,
        )
    )
    if db.info.get("read_store_id") is not None:
        statement = statement.where(InventoryBatch.store_id == db.info["read_store_id"])
    if lock:
        statement = statement.with_for_update().execution_options(populate_existing=True)
    return await db.scalars(statement)


def add_discard_record(db, record):
    """执行record_discard所需的数据库新增；权限由调用它的服务检查。"""
    return db.add(record)


async def get_remaining_batch_quantities(db, product):
    """执行record_discard所需的数据库查询；权限由调用它的服务检查。"""
    store_query_1 = (
        select(InventoryBatch.remaining_quantity)
        .where(InventoryBatch.store_id == product.store_id, InventoryBatch.product_id == product.id)
        .with_for_update()
    )
    if db.info.get("read_store_id") is not None:
        store_query_1 = store_query_1.where(InventoryBatch.store_id == db.info["read_store_id"])
    return await db.scalars(store_query_1)


async def get_discard_by_request_id(db, product, request):
    """执行create_discard所需的数据库查询；权限由调用它的服务检查。"""
    store_query_2 = (
        select(InventoryDiscard)
        .where(
            InventoryDiscard.store_id == product.store_id,
            InventoryDiscard.request_key == str(request.request_id),
        )
        .with_for_update()
        .options(lazyload(InventoryDiscard.items))
        .execution_options(populate_existing=True)
    )
    if db.info.get("read_store_id") is not None:
        store_query_2 = store_query_2.where(InventoryDiscard.store_id == db.info["read_store_id"])
    return await db.scalar(store_query_2)


async def get_discard_items_for_update(db, existing):
    """执行create_discard所需的数据库查询；权限由调用它的服务检查。"""
    store_query_3 = (
        select(InventoryDiscardItem)
        .where(InventoryDiscardItem.discard_id == existing.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if db.info.get("read_store_id") is not None:
        store_query_3 = store_query_3.where(
            InventoryDiscardItem.store_id == db.info["read_store_id"]
        )
    return await db.scalars(store_query_3)


async def get_discard_totals(db, employee, request, selected):
    """构建并执行list_discards_execute的查询，店铺条件在这里明确添加。"""
    conditions = []
    if request.product_id is not None:
        conditions.append(InventoryDiscard.product_id == request.product_id)
    if request.department_id is not None:
        conditions.append(InventoryDiscard.department_id == request.department_id)
    if request.reason_code:
        conditions.append(InventoryDiscard.reason_code == request.reason_code)
    if request.mode:
        if request.mode == "automatic":
            selected_value = InventoryDiscard.employee_id.is_(None)
        else:
            selected_value = InventoryDiscard.employee_id.is_not(None)
        conditions.append(selected_value)
    if request.start_date:
        conditions.append(
            InventoryDiscard.created_at >= datetime.combine(request.start_date, time.min)
        )
    if request.end_date:
        conditions.append(
            InventoryDiscard.created_at
            < datetime.combine(request.end_date + timedelta(days=1), time.min)
        )
    if selected is not None:
        conditions.append(InventoryDiscard.store_id == selected)
    if employee.role == EmployeeRole.REGULAR_EMPLOYEE:
        conditions.append(InventoryDiscard.department_id == employee.department_id)
    store_query_4 = select(
        func.count(InventoryDiscard.id),
        func.coalesce(func.sum(InventoryDiscard.quantity), 0),
        func.coalesce(func.sum(InventoryDiscard.total_cost), 0),
    ).where(*conditions)
    if db.info.get("read_store_id") is not None:
        store_query_4 = store_query_4.where(InventoryDiscard.store_id == db.info["read_store_id"])
    return await db.execute(store_query_4)


async def get_discard_page(db, employee, request, selected):
    """执行list_discards所需的数据库查询；权限由调用它的服务检查。"""
    conditions = []
    if request.product_id is not None:
        conditions.append(InventoryDiscard.product_id == request.product_id)
    if request.department_id is not None:
        conditions.append(InventoryDiscard.department_id == request.department_id)
    if request.reason_code:
        conditions.append(InventoryDiscard.reason_code == request.reason_code)
    if request.mode:
        if request.mode == "automatic":
            selected_value_item = InventoryDiscard.employee_id.is_(None)
        else:
            selected_value_item = InventoryDiscard.employee_id.is_not(None)
        conditions.append(selected_value_item)
    if request.start_date:
        conditions.append(
            InventoryDiscard.created_at >= datetime.combine(request.start_date, time.min)
        )
    if request.end_date:
        conditions.append(
            InventoryDiscard.created_at
            < datetime.combine(request.end_date + timedelta(days=1), time.min)
        )
    if selected is not None:
        conditions.append(InventoryDiscard.store_id == selected)
    if employee.role == EmployeeRole.REGULAR_EMPLOYEE:
        conditions.append(InventoryDiscard.department_id == employee.department_id)
    store_query_4 = select(
        func.count(InventoryDiscard.id),
        func.coalesce(func.sum(InventoryDiscard.quantity), 0),
        func.coalesce(func.sum(InventoryDiscard.total_cost), 0),
    ).where(*conditions)
    if db.info.get("read_store_id") is not None:
        store_query_4 = store_query_4.where(InventoryDiscard.store_id == db.info["read_store_id"])
    store_query_5 = (
        select(InventoryDiscard)
        .where(*conditions)
        .order_by(InventoryDiscard.created_at.desc(), InventoryDiscard.id.desc())
        .offset((request.page - 1) * request.page_size)
        .limit(request.page_size)
    )
    if db.info.get("read_store_id") is not None:
        store_query_5 = store_query_5.where(InventoryDiscard.store_id == db.info["read_store_id"])
    return await db.scalars(store_query_5)


async def get_expired_product_for_update(db, product_id):
    """执行discard_expired_product所需的数据库查询；权限由调用它的服务检查。"""
    store_query_6 = (
        select(Product)
        .where(Product.id == product_id)
        .options(selectinload(Product.department))
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if db.info.get("read_store_id") is not None:
        store_query_6 = store_query_6.where(Product.store_id == db.info["read_store_id"])
    return await db.scalar(store_query_6)


async def get_expired_product_batches(db, current_date, product):
    """执行discard_expired_product所需的数据库查询；权限由调用它的服务检查。"""
    store_query_7 = (
        select(InventoryBatch)
        .where(
            InventoryBatch.product_id == product.id,
            InventoryBatch.store_id == product.store_id,
            InventoryBatch.expiration_date < current_date,
            InventoryBatch.remaining_quantity > 0,
        )
        .options(selectinload(InventoryBatch.purchase_item))
        .order_by(InventoryBatch.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if db.info.get("read_store_id") is not None:
        store_query_7 = store_query_7.where(InventoryBatch.store_id == db.info["read_store_id"])
    return await db.scalars(store_query_7)
