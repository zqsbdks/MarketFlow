"""replenishment：数据库读写函数。"""

from datetime import datetime, time, timedelta

from sqlalchemy import func, select
from sqlalchemy.dialects.mysql import insert as mysql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import selectinload

from app.models.category import Category
from app.models.employee import Employee
from app.models.enums import EmployeeRole
from app.models.inventory_batch import InventoryBatch
from app.models.product import Product
from app.models.purchase import Purchase
from app.models.purchase_item import PurchaseItem
from app.models.purchase_plan import PurchasePlan
from app.models.sale import Sale
from app.models.sale_item import SaleItem
from app.models.store import Store, StoreDepartment
from app.models.supplier_product import SupplierProduct


async def get_recent_daily_sales(db, product_ids, store_id, today):
    """执行weekday_sales_forecast所需的数据库查询或更新；权限由调用它的服务检查。"""
    store_query_1 = (
        select(SaleItem.product_id, func.date(Sale.sold_at), func.sum(SaleItem.quantity))
        .join(Sale, Sale.id == SaleItem.sale_id)
        .where(
            Sale.store_id == store_id,
            Sale.sold_at >= datetime.combine(today - timedelta(days=28), time.min),
            Sale.sold_at < datetime.combine(today, time.min),
            SaleItem.product_id.in_(product_ids),
        )
        .group_by(SaleItem.product_id, func.date(Sale.sold_at))
    )
    if db.info.get("read_store_id") is not None:
        store_query_1 = store_query_1.where(SaleItem.store_id == db.info["read_store_id"])
    if db.info.get("read_store_id") is not None:
        store_query_1 = store_query_1.where(Sale.store_id == db.info["read_store_id"])
    return await db.execute(store_query_1)


async def get_automatic_plan_employee(db, department_id, store_id):
    """执行refresh_automatic_plans所需的数据库查询；权限由调用它的服务检查。"""
    store_query_2 = (
        select(Employee.id)
        .where(
            Employee.store_id == store_id,
            Employee.is_active.is_(True),
            (Employee.role == EmployeeRole.STORE_MANAGER)
            | (Employee.role == EmployeeRole.REGULAR_EMPLOYEE)
            & (Employee.department_id == department_id),
        )
        .order_by(Employee.id)
        .limit(1)
    )
    if (
        db.info.get("private_employee_path")
        and db.info.get("actor_role") != EmployeeRole.HEADQUARTERS
    ):
        store_query_2 = store_query_2.where(Employee.store_id == db.info["own_store_id"])
    return await db.scalar(store_query_2)


async def get_enabled_store_departments(db):
    """执行refresh_automatic_plans所需的数据库查询或更新；权限由调用它的服务检查。"""
    return await db.execute(
        select(StoreDepartment.store_id, StoreDepartment.department_id)
        .join(Store, Store.id == StoreDepartment.store_id)
        .where(Store.is_active.is_(True), StoreDepartment.is_active.is_(True))
        .order_by(StoreDepartment.store_id, StoreDepartment.department_id)
    )


async def get_automatic_plan_for_update(db, day, department_id, store_id):
    """执行refresh_automatic_plans所需的数据库查询；权限由调用它的服务检查。"""
    store_query_3 = (
        select(PurchasePlan)
        .where(
            PurchasePlan.store_id == store_id,
            PurchasePlan.department_id == department_id,
            PurchasePlan.arrival_date == day,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if db.info.get("read_store_id") is not None:
        store_query_3 = store_query_3.where(PurchasePlan.store_id == db.info["read_store_id"])
    return await db.scalar(store_query_3)


async def get_automatic_plan_catalog(db, department_id, store_id):
    """执行refresh_automatic_plans所需的数据库查询；权限由调用它的服务检查。"""
    store_query_4 = (
        select(SupplierProduct)
        .join(Category)
        .options(selectinload(SupplierProduct.supplier))
        .where(
            SupplierProduct.store_id == store_id,
            Category.department_id == department_id,
            SupplierProduct.is_active.is_(True),
            SupplierProduct.shelf_life_days.is_not(None),
        )
    )
    if db.info.get("read_store_id") is not None:
        store_query_4 = store_query_4.where(SupplierProduct.store_id == db.info["read_store_id"])
    return await db.scalars(store_query_4)


async def insert_automatic_plan_mysql(db, values):
    """构建并执行refresh_automatic_plans_execute_2的查询，店铺条件在这里明确添加。"""
    statement = mysql_insert(PurchasePlan).values(**values)
    return await db.execute(statement.on_duplicate_key_update(id=PurchasePlan.id))


async def insert_automatic_plan_sqlite(db, values):
    """构建并执行refresh_automatic_plans_execute_3的查询，店铺条件在这里明确添加。"""
    statement_sqlite = sqlite_insert(PurchasePlan).values(**values)
    return await db.execute(
        statement_sqlite.on_conflict_do_nothing(
            index_elements=["store_id", "department_id", "arrival_date"]
        )
    )


async def get_replenishment_products(db, catalog_ids, store_id):
    """执行calculate_replenishment所需的数据库查询；权限由调用它的服务检查。"""
    store_query_5 = select(Product).where(
        Product.store_id == store_id, Product.supplier_product_id.in_(catalog_ids)
    )
    if db.info.get("read_store_id") is not None:
        store_query_5 = store_query_5.where(Product.store_id == db.info["read_store_id"])
    return await db.scalars(store_query_5)


async def get_replenishment_batches(db, catalog_by_product, store_id):
    """执行calculate_replenishment所需的数据库查询或更新；权限由调用它的服务检查。"""
    store_query_6 = select(
        InventoryBatch.product_id,
        InventoryBatch.arrived_at,
        InventoryBatch.expiration_date,
        InventoryBatch.remaining_quantity,
    ).where(
        InventoryBatch.store_id == store_id,
        InventoryBatch.product_id.in_(catalog_by_product),
        InventoryBatch.remaining_quantity > 0,
    )
    if db.info.get("read_store_id") is not None:
        store_query_6 = store_query_6.where(InventoryBatch.store_id == db.info["read_store_id"])
    return await db.execute(store_query_6)


async def get_pending_arrival_items(db, catalog_ids, days, store_id):
    """执行calculate_replenishment所需的数据库查询或更新；权限由调用它的服务检查。"""
    store_query_7 = (
        select(
            PurchaseItem.supplier_product_id,
            Purchase.expected_arrival_at,
            PurchaseItem.expiration_date,
            PurchaseItem.quantity,
        )
        .join(Purchase, Purchase.id == PurchaseItem.purchase_id)
        .where(
            Purchase.store_id == store_id,
            Purchase.status == "pending",
            PurchaseItem.supplier_product_id.in_(catalog_ids),
            Purchase.expected_arrival_at
            < datetime.combine(max(days) + timedelta(days=1), time.min),
        )
    )
    if db.info.get("read_store_id") is not None:
        store_query_7 = store_query_7.where(PurchaseItem.store_id == db.info["read_store_id"])
    if db.info.get("read_store_id") is not None:
        store_query_7 = store_query_7.where(Purchase.store_id == db.info["read_store_id"])
    return await db.execute(store_query_7)


async def get_replenishment_plans(db, days, department_id, store_id, today):
    """执行calculate_replenishment所需的数据库查询；权限由调用它的服务检查。"""
    store_query_8 = select(PurchasePlan).where(
        PurchasePlan.store_id == store_id,
        PurchasePlan.department_id == department_id,
        PurchasePlan.arrival_date >= today,
        PurchasePlan.arrival_date <= max(days),
    )
    if db.info.get("read_store_id") is not None:
        store_query_8 = store_query_8.where(PurchasePlan.store_id == db.info["read_store_id"])
    return await db.scalars(store_query_8)
