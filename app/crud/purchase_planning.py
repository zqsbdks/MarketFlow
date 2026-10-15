"""purchase_planning：数据库读写函数。"""

from datetime import datetime, time, timedelta

from sqlalchemy import func, or_, select
from sqlalchemy.orm import selectinload

from app.models.category import Category
from app.models.inventory_batch import InventoryBatch
from app.models.product import Product
from app.models.purchase import Purchase
from app.models.purchase_item import PurchaseItem
from app.models.purchase_plan import PurchasePlan
from app.models.sale import Sale
from app.models.sale_item import SaleItem
from app.models.supplier_product import SupplierProduct


async def get_visible_purchase_plans(db, days, department_id, store_id):
    """执行get_purchase_planning所需的数据库查询；权限由调用它的服务检查。"""
    store_query_1 = select(PurchasePlan).where(
        PurchasePlan.store_id == store_id,
        PurchasePlan.department_id == department_id,
        PurchasePlan.arrival_date.in_(days),
    )
    if db.info.get("read_store_id") is not None:
        store_query_1 = store_query_1.where(PurchasePlan.store_id == db.info["read_store_id"])
    return await db.scalars(store_query_1)


async def get_department_catalog(db, department_id):
    """执行get_purchase_planning所需的数据库查询；权限由调用它的服务检查。"""
    store_query_2 = (
        select(SupplierProduct)
        .join(Category, SupplierProduct.category_id == Category.id)
        .options(selectinload(SupplierProduct.supplier))
        .where(Category.department_id == department_id, SupplierProduct.is_active.is_(True))
        .order_by(SupplierProduct.name, SupplierProduct.id)
    )
    if db.info.get("read_store_id") is not None:
        store_query_2 = store_query_2.where(SupplierProduct.store_id == db.info["read_store_id"])
    return await db.scalars(store_query_2)


async def get_catalog_products(db, catalog_ids, store_id):
    """执行get_purchase_planning所需的数据库查询；权限由调用它的服务检查。"""
    store_query_3 = select(Product).where(
        Product.store_id == store_id, Product.supplier_product_id.in_(catalog_ids)
    )
    if db.info.get("read_store_id") is not None:
        store_query_3 = store_query_3.where(Product.store_id == db.info["read_store_id"])
    return await db.scalars(store_query_3)


async def get_scheduled_arrivals(db, catalog_ids, range_end, range_start, store_id):
    """执行get_purchase_planning所需的数据库查询或更新；权限由调用它的服务检查。"""
    store_query_4 = (
        select(
            PurchaseItem.supplier_product_id,
            Purchase.status,
            func.date(Purchase.expected_arrival_at),
            func.date(Purchase.arrived_at),
            func.sum(PurchaseItem.quantity),
        )
        .join(Purchase, PurchaseItem.purchase_id == Purchase.id)
        .where(
            Purchase.store_id == store_id,
            PurchaseItem.supplier_product_id.in_(catalog_ids),
            or_(
                Purchase.expected_arrival_at.between(range_start, range_end),
                Purchase.arrived_at.between(range_start, range_end),
            ),
        )
        .group_by(
            PurchaseItem.supplier_product_id,
            Purchase.status,
            func.date(Purchase.expected_arrival_at),
            func.date(Purchase.arrived_at),
        )
    )
    if db.info.get("read_store_id") is not None:
        store_query_4 = store_query_4.where(PurchaseItem.store_id == db.info["read_store_id"])
    if db.info.get("read_store_id") is not None:
        store_query_4 = store_query_4.where(Purchase.store_id == db.info["read_store_id"])
    return await db.execute(store_query_4)


async def get_last_week_sales(db, first_day, product_ids, store_id):
    """执行get_purchase_planning所需的数据库查询或更新；权限由调用它的服务检查。"""
    store_query_5 = (
        select(SaleItem.product_id, func.date(Sale.sold_at), func.sum(SaleItem.quantity))
        .join(Sale, SaleItem.sale_id == Sale.id)
        .where(
            Sale.store_id == store_id,
            SaleItem.product_id.in_(product_ids),
            Sale.sold_at >= datetime.combine(first_day - timedelta(days=7), time.min),
            Sale.sold_at < datetime.combine(first_day, time.min),
        )
        .group_by(SaleItem.product_id, func.date(Sale.sold_at))
    )
    if db.info.get("read_store_id") is not None:
        store_query_5 = store_query_5.where(SaleItem.store_id == db.info["read_store_id"])
    if db.info.get("read_store_id") is not None:
        store_query_5 = store_query_5.where(Sale.store_id == db.info["read_store_id"])
    return await db.execute(store_query_5)


async def get_saleable_batch_stock(db, product_ids, store_id):
    """执行get_purchase_planning所需的数据库查询或更新；权限由调用它的服务检查。"""
    store_query_6 = select(
        InventoryBatch.product_id, InventoryBatch.expiration_date, InventoryBatch.remaining_quantity
    ).where(
        InventoryBatch.store_id == store_id,
        InventoryBatch.product_id.in_(product_ids),
        InventoryBatch.remaining_quantity > 0,
    )
    if db.info.get("read_store_id") is not None:
        store_query_6 = store_query_6.where(InventoryBatch.store_id == db.info["read_store_id"])
    return await db.execute(store_query_6)
