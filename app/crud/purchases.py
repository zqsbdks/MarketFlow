"""进货管理的数据访问函数。"""

from datetime import date, datetime, time, timedelta

from sqlalchemy import Integer, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.sql.elements import ColumnElement

from app.models.employee import Employee
from app.models.enums import EmployeeRole, PurchaseStatus
from app.models.inventory_batch import InventoryBatch
from app.models.product import Product
from app.models.purchase import Purchase
from app.models.purchase_item import PurchaseItem
from app.models.supplier_product import SupplierProduct


# region 获取进货单列表
async def get_all_purchases(
    offset: int,
    page_size: int,
    purchase_no: str | None,
    department_id: int | None,
    ordered_at: date | None,
    arrived_at: date | None,
    purchase_status: PurchaseStatus | None,
    db: AsyncSession,
) -> tuple[list[tuple[Purchase, int, int]], int]:
    """分页查询进货单，同时统计每张单的明细数和商品总数量。"""
    conditions: list[ColumnElement[bool]] = []
    if purchase_no is not None:
        conditions.append(Purchase.purchase_no.ilike(f"%{purchase_no}%"))
    if department_id is not None:
        conditions.append(Purchase.department_id == department_id)
    if purchase_status is not None:
        conditions.append(Purchase.status == purchase_status)
    if ordered_at is not None:
        day_start = datetime.combine(ordered_at, time.min)
        next_day_start = day_start + timedelta(days=1)
        conditions.append(Purchase.ordered_at >= day_start)
        conditions.append(Purchase.ordered_at < next_day_start)
    if arrived_at is not None:
        arrival_day_start = datetime.combine(arrived_at, time.min)
        next_arrival_day_start = arrival_day_start + timedelta(days=1)
        conditions.append(Purchase.arrived_at >= arrival_day_start)
        conditions.append(Purchase.arrived_at < next_arrival_day_start)
    store_query_1 = select(
        PurchaseItem.purchase_id.label("purchase_id"),
        func.count(PurchaseItem.id).label("item_count"),
        func.coalesce(func.sum(PurchaseItem.quantity), 0).label("total_quantity"),
    ).group_by(PurchaseItem.purchase_id)
    if db.info.get("read_store_id") is not None:
        store_query_1 = store_query_1.where(PurchaseItem.store_id == db.info["read_store_id"])
    item_summary = store_query_1.subquery()
    list_statement = (
        select(
            Purchase,
            func.coalesce(item_summary.c.item_count, 0),
            func.coalesce(item_summary.c.total_quantity, 0),
        )
        .outerjoin(item_summary, item_summary.c.purchase_id == Purchase.id)
        .options(
            selectinload(Purchase.department),
            selectinload(Purchase.created_by_employee),
            selectinload(Purchase.received_by_employee),
        )
        .where(*conditions)
        .order_by(Purchase.ordered_at.desc(), Purchase.id.desc())
        .offset(offset)
        .limit(page_size)
    )
    if db.info.get("read_store_id") is not None:
        list_statement = list_statement.where(Purchase.store_id == db.info["read_store_id"])
    count_statement = select(func.count(Purchase.id)).where(*conditions)
    if db.info.get("read_store_id") is not None:
        count_statement = count_statement.where(Purchase.store_id == db.info["read_store_id"])
    total = int(await db.scalar(count_statement) or 0)
    query_result = await db.execute(list_statement)
    purchases: list[tuple[Purchase, int, int]] = []
    for purchase, item_count, total_quantity in query_result.all():
        purchases.append((purchase, int(item_count), int(total_quantity)))
    return (purchases, total)


# endregion


# region 获取进货单详情
async def get_purchase_by_id(purchase_id: int, db: AsyncSession) -> Purchase | None:
    """根据ID查询进货单，并加载部门、员工和全部进货明细。"""
    statement = (
        select(Purchase)
        .options(
            selectinload(Purchase.department),
            selectinload(Purchase.created_by_employee),
            selectinload(Purchase.received_by_employee),
            selectinload(Purchase.items),
        )
        .where(Purchase.id == purchase_id)
        .execution_options(populate_existing=True)
    )
    if db.info.get("read_store_id") is not None:
        statement = statement.where(Purchase.store_id == db.info["read_store_id"])
    result = await db.execute(statement)
    return result.scalar_one_or_none()


async def get_purchase_by_client_request_id(
    client_request_id: str, db: AsyncSession
) -> Purchase | None:
    """按客户端幂等ID查询已创建的进货单。"""
    store_query_5 = select(Purchase).where(Purchase.client_request_id == client_request_id)
    if db.info.get("read_store_id") is not None:
        store_query_5 = store_query_5.where(Purchase.store_id == db.info["read_store_id"])
    result = await db.execute(store_query_5)
    return result.scalar_one_or_none()


# endregion


# region 创建进货单


# endregion


# region 自动签收到货


# endregion


__all__ = [
    "get_all_purchases",
    "get_purchase_by_client_request_id",
    "get_purchase_by_id",
]


def add_purchase_record(db, new_purchase):
    """执行create_purchase_records所需的数据库新增；权限由调用它的服务检查。"""
    return db.add(new_purchase)


async def get_order_catalog(db, supplier_product_ids):
    """构建并执行create_purchase_records_query的查询，店铺条件在这里明确添加。"""
    catalog_statement = (
        select(SupplierProduct)
        .options(selectinload(SupplierProduct.supplier), selectinload(SupplierProduct.products))
        .where(SupplierProduct.id.in_(supplier_product_ids))
    )
    if db.info.get("read_store_id") is not None:
        catalog_statement = catalog_statement.where(
            SupplierProduct.store_id == db.info["read_store_id"]
        )
    return await db.scalars(catalog_statement)


def add_received_batch(db, inventory_batch):
    """执行auto_receive_due_purchases所需的数据库新增；权限由调用它的服务检查。"""
    return db.add(inventory_batch)


async def get_latest_product_number(db):
    """构建并执行auto_receive_due_purchases_query的查询，店铺条件在这里明确添加。"""
    store_query_8 = select(
        func.coalesce(func.max(cast(func.substr(Product.product_no, 2), Integer)), 0)
    )
    if db.info.get("read_store_id") is not None:
        store_query_8 = store_query_8.where(Product.store_id == db.info["read_store_id"])
    return await db.scalar(store_query_8)


async def get_latest_batch_number(db, arrived_at):
    """构建并执行auto_receive_due_purchases_query_2的查询，店铺条件在这里明确添加。"""
    store_query_9 = select(
        func.coalesce(func.max(cast(func.substr(InventoryBatch.batch_no, 12), Integer)), 0)
    ).where(InventoryBatch.batch_no.like(f"BAT{arrived_at:%Y%m%d}%"))
    if db.info.get("read_store_id") is not None:
        store_query_9 = store_query_9.where(InventoryBatch.store_id == db.info["read_store_id"])
    return await db.scalar(store_query_9)


async def get_default_receiving_employee(db, purchase):
    """构建并执行auto_receive_due_purchases_query_3的查询，店铺条件在这里明确添加。"""
    store_query_10 = (
        select(Employee)
        .where(
            Employee.department_id == purchase.department_id,
            Employee.store_id == purchase.store_id,
            Employee.role == EmployeeRole.REGULAR_EMPLOYEE,
            Employee.is_active.is_(True),
        )
        .order_by(Employee.id.asc())
        .limit(1)
    )
    if (
        db.info.get("private_employee_path")
        and db.info.get("actor_role") != EmployeeRole.HEADQUARTERS
    ):
        store_query_10 = store_query_10.where(Employee.store_id == db.info["own_store_id"])
    return await db.scalar(store_query_10)


async def get_manual_receiving_employee(db, employee_id):
    """执行auto_receive_due_purchases所需的数据库查询；权限由调用它的服务检查。"""
    return await db.get(Employee, employee_id)


async def get_received_product(db, catalog_product, purchase):
    """构建并执行auto_receive_due_purchases_query_4的查询，店铺条件在这里明确添加。"""
    store_query_11 = (
        select(Product)
        .where(
            Product.supplier_product_id == catalog_product.id, Product.store_id == purchase.store_id
        )
        .with_for_update()
    )
    if db.info.get("read_store_id") is not None:
        store_query_11 = store_query_11.where(Product.store_id == db.info["read_store_id"])
    return await db.scalar(store_query_11)


def add_received_product(db, product):
    """执行auto_receive_due_purchases所需的数据库新增；权限由调用它的服务检查。"""
    return db.add(product)


async def get_due_purchases(db, arrived_at, only_purchase_id):
    """构建并执行auto_receive_due_purchases_query_5的查询，店铺条件在这里明确添加。"""
    conditions = [Purchase.status == PurchaseStatus.PENDING]
    if only_purchase_id is None:
        conditions.append(Purchase.expected_arrival_at <= arrived_at)
    else:
        conditions.append(Purchase.id == only_purchase_id)
    statement = (
        select(Purchase)
        .options(
            selectinload(Purchase.items)
            .selectinload(PurchaseItem.supplier_product)
            .selectinload(SupplierProduct.products),
            selectinload(Purchase.items)
            .selectinload(PurchaseItem.supplier_product)
            .selectinload(SupplierProduct.category),
        )
        .where(*conditions)
        .order_by(Purchase.id.asc())
        .with_for_update()
    )
    if db.info.get("read_store_id") is not None:
        statement = statement.where(Purchase.store_id == db.info["read_store_id"])
    return await db.scalars(statement)
