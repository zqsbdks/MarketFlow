"""进货计划表：未来七天已有到货安排与上周同曜日销售参考。"""

from datetime import date, datetime, time, timedelta

from fastapi import HTTPException
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.business_time import business_now
from app.models.category import Category
from app.models.inventory_batch import InventoryBatch
from app.models.product import Product
from app.models.purchase import Purchase
from app.models.purchase_item import PurchaseItem
from app.models.sale import Sale
from app.models.sale_item import SaleItem
from app.models.supplier_product import SupplierProduct


# region 组装七天计划表
async def get_purchase_planning(
    department_id: int, arrival_date: date | None, db: AsyncSession
) -> dict:
    """每种供应商品一行；历史销量与已有订单只作参考，不自动生成订货量。"""
    today = business_now().date()
    first_day = arrival_date or today + timedelta(days=2)
    if not today <= first_day <= today + timedelta(days=30):
        raise HTTPException(400, "预计到货日期须在今天至30天内")
    store_id = db.info.get("read_store_id")
    if store_id is None:
        raise HTTPException(400, "请先选择门店")
    days = [first_day + timedelta(days=offset) for offset in range(7)]
    day_keys = {day.isoformat() for day in days}
    range_start = datetime.combine(first_day, time.min)
    range_end = datetime.combine(days[-1] + timedelta(days=1), time.min)
    catalog = (await db.scalars(
        select(SupplierProduct).join(Category, SupplierProduct.category_id == Category.id)
        .options(selectinload(SupplierProduct.supplier))
        .where(Category.department_id == department_id, SupplierProduct.is_active.is_(True))
        .order_by(SupplierProduct.name, SupplierProduct.id)
    )).all()
    catalog = [item for item in catalog if item.supplier is not None and item.supplier.is_active]
    if not catalog:
        return {"arrival_date": first_day, "days": days, "items": []}
    catalog_ids = [item.id for item in catalog]
    products = (await db.scalars(select(Product).where(
        Product.store_id == store_id, Product.supplier_product_id.in_(catalog_ids)
    ))).all()
    by_catalog = {item.supplier_product_id: item for item in products}
    product_ids = [item.id for item in products]
    warning_days = {item.id: item.expiry_warning_days for item in products}

    # 已有进货单按“预计到货日”累计，已签收的用实际到货日累计。
    arrival_rows = (await db.execute(
        select(PurchaseItem.supplier_product_id, Purchase.status,
               func.date(Purchase.expected_arrival_at), func.date(Purchase.arrived_at),
               func.sum(PurchaseItem.quantity))
        .join(Purchase, PurchaseItem.purchase_id == Purchase.id)
        .where(Purchase.store_id == store_id,
               PurchaseItem.supplier_product_id.in_(catalog_ids),
               or_(
                   Purchase.expected_arrival_at.between(range_start, range_end),
                   Purchase.arrived_at.between(range_start, range_end),
               ))
        .group_by(PurchaseItem.supplier_product_id, Purchase.status,
                  func.date(Purchase.expected_arrival_at), func.date(Purchase.arrived_at))
    )).all()
    arrivals: dict[tuple[int, str], dict[str, int]] = {}
    for catalog_id, status, expected, actual, quantity in arrival_rows:
        day = str(actual if status == "arrived" and actual else expected)
        if day not in day_keys:
            continue
        bucket = arrivals.setdefault((catalog_id, day), {"expected": 0, "received": 0})
        bucket["received" if status == "arrived" else "expected"] += int(quantity)

    sold: dict[tuple[int, str], int] = {}
    stock: dict[int, int] = {}
    expiring: dict[int, int] = {}
    if product_ids:
        sold_rows = (await db.execute(
            select(SaleItem.product_id, func.date(Sale.sold_at), func.sum(SaleItem.quantity))
            .join(Sale, SaleItem.sale_id == Sale.id)
            .where(Sale.store_id == store_id, SaleItem.product_id.in_(product_ids),
                   Sale.sold_at >= datetime.combine(first_day - timedelta(days=7), time.min),
                   Sale.sold_at < datetime.combine(first_day, time.min))
            .group_by(SaleItem.product_id, func.date(Sale.sold_at))
        )).all()
        for product_id, day, quantity in sold_rows:
            sold[(product_id, str(day))] = int(quantity)
        batch_rows = (await db.execute(
            select(InventoryBatch.product_id, InventoryBatch.expiration_date,
                   InventoryBatch.remaining_quantity)
            .where(InventoryBatch.store_id == store_id,
                   InventoryBatch.product_id.in_(product_ids),
                   InventoryBatch.remaining_quantity > 0)
        )).all()
        for product_id, expires, quantity in batch_rows:
            if expires is None or expires >= today:
                stock[product_id] = stock.get(product_id, 0) + quantity
                if (expires is not None and warning_days[product_id] is not None
                        and expires <= today + timedelta(days=warning_days[product_id])):
                    expiring[product_id] = expiring.get(product_id, 0) + quantity

    items = []
    for catalog_item in catalog:
        product = by_catalog.get(catalog_item.id)
        product_id = product.id if product else None
        daily = []
        for day in days:
            arrival = arrivals.get((catalog_item.id, day.isoformat()), {})
            daily.append({
                "date": day,
                "expected_quantity": arrival.get("expected", 0),
                "received_quantity": arrival.get("received", 0),
                "last_week_sales": sold.get((product_id, (day - timedelta(days=7)).isoformat()), 0),
            })
        items.append({
            "supplier_product_id": catalog_item.id,
            "product_id": product_id,
            "name": catalog_item.name,
            "supplier_name": catalog_item.supplier.name,
            "unit_cost": catalog_item.unit_cost,
            "saleable_stock": stock.get(product_id, 0),
            "near_expiry_stock_quantity": expiring.get(product_id, 0),
            "days": daily,
        })
    return {"arrival_date": first_day, "days": days, "items": items}
# endregion


__all__ = ["get_purchase_planning"]
