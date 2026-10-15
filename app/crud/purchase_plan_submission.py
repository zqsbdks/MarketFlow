"""purchase_plan_submission：数据库读写函数。"""

from sqlalchemy import select
from sqlalchemy.dialects.mysql import insert as mysql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import selectinload

from app.models.category import Category
from app.models.employee import Employee
from app.models.product import Product
from app.models.purchase_plan import PurchasePlan
from app.models.store import StoreDepartment
from app.models.supplier_product import SupplierProduct


async def get_plan_writer(db, actor_id):
    """执行validate_plan_writer所需的数据库查询；权限由调用它的服务检查。"""
    return await db.get(Employee, actor_id)


async def get_plan_department_enabled(db, request, store_id):
    """执行validate_plan_writer所需的数据库查询；权限由调用它的服务检查。"""
    return await db.scalar(
        select(StoreDepartment.is_active).where(
            StoreDepartment.store_id == store_id,
            StoreDepartment.department_id == request.department_id,
        )
    )


async def get_writable_catalog_product(db, request, store_id):
    """执行validate_plan_writer所需的数据库查询；权限由调用它的服务检查。"""
    store_query_1 = (
        select(SupplierProduct)
        .join(Category)
        .options(selectinload(SupplierProduct.supplier))
        .where(
            SupplierProduct.id == request.supplier_product_id,
            SupplierProduct.store_id == store_id,
            Category.department_id == request.department_id,
        )
    )
    if db.info.get("read_store_id") is not None:
        store_query_1 = store_query_1.where(SupplierProduct.store_id == db.info["read_store_id"])
    return await db.scalar(store_query_1)


async def get_catalog_product_ids(db, catalog):
    """执行save_minimum_stock所需的数据库查询；权限由调用它的服务检查。"""
    store_query_2 = select(Product.id).where(
        Product.store_id == catalog.store_id, Product.supplier_product_id == catalog.id
    )
    if db.info.get("read_store_id") is not None:
        store_query_2 = store_query_2.where(Product.store_id == db.info["read_store_id"])
    return await db.scalars(store_query_2)


async def get_plan_for_update(db, request, store_id):
    """构建并执行save_purchase_plan_query的查询，店铺条件在这里明确添加。"""
    statement = (
        select(PurchasePlan)
        .where(
            PurchasePlan.store_id == store_id,
            PurchasePlan.department_id == request.department_id,
            PurchasePlan.arrival_date == request.arrival_date,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if db.info.get("read_store_id") is not None:
        statement = statement.where(PurchasePlan.store_id == db.info["read_store_id"])
    return await db.scalar(statement)


async def insert_plan_if_missing_mysql(db, values):
    """构建并执行save_purchase_plan_execute的查询，店铺条件在这里明确添加。"""
    insert = mysql_insert(PurchasePlan).values(**values)
    return await db.execute(insert.on_duplicate_key_update(id=PurchasePlan.id))


async def insert_plan_if_missing_sqlite(db, values):
    """构建并执行save_purchase_plan_execute_2的查询，店铺条件在这里明确添加。"""
    insert_sqlite = sqlite_insert(PurchasePlan).values(**values)
    return await db.execute(
        insert_sqlite.on_conflict_do_nothing(
            index_elements=["store_id", "department_id", "arrival_date"]
        )
    )


async def get_submission_plan_for_update(db, plan_id):
    """执行submit_due_plan所需的数据库查询；权限由调用它的服务检查。"""
    store_query_3 = (
        select(PurchasePlan)
        .where(PurchasePlan.id == plan_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if db.info.get("read_store_id") is not None:
        store_query_3 = store_query_3.where(PurchasePlan.store_id == db.info["read_store_id"])
    return await db.scalar(store_query_3)
