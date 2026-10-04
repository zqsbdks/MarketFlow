"""按门店销量、批次保质期和已订到货量逐日推演补货。"""

from datetime import date, datetime, time, timedelta
from math import ceil

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.inventory_batch import InventoryBatch
from app.models.product import Product
from app.models.purchase import Purchase
from app.models.purchase_item import PurchaseItem
from app.models.purchase_plan import PurchasePlan
from app.models.sale import Sale
from app.models.sale_item import SaleItem


def simulate_replenishment(
    now, days, sales, batches, incoming, minimum_stock, shelf_life, overrides
):
    """保底值是销售后的目标余量，不是最低订货量；每日只补一天的预计需求。"""
    stock = [list(batch) for batch in batches]  # [可用日期，到期日期，数量]
    result = {}
    first = now.date()
    last = max(days)
    day = first
    while day <= last:
        stock = [batch for batch in stock if batch[1] is None or batch[1] >= day]
        for arrival, expires, quantity in incoming:
            if arrival == day and (expires is None or expires >= day):
                stock.append([day, expires, quantity])
        demand = sales.get(day.weekday(), 0)
        if day == first:
            remaining_hours = max(
                0, min(12, (datetime.combine(day, time(21)) - now).total_seconds() / 3600)
            )
            demand = ceil(demand * remaining_hours / 12)
        available = sum(batch[2] for batch in stock if batch[0] <= day)
        if day in days:
            suggestion = min(1000000, max(0, ceil(demand + minimum_stock - available)))
            quantity = overrides.get(day, suggestion)
            result[day] = {
                "suggested_quantity": suggestion,
                "planned_quantity": quantity,
                "is_manual": day in overrides,
                "forecast_sales": demand,
                "projected_stock": available,
                "target_stock": demand + minimum_stock,
            }
            if quantity and shelf_life is not None:
                stock.append([day, day + timedelta(days=shelf_life), quantity])
        # 先销售先过期批次；未到货的批次不能提前使用。
        stock.sort(key=lambda batch: batch[1] or date.max)
        remaining = demand
        for batch in stock:
            if batch[0] > day:
                continue
            used = min(batch[2], remaining)
            batch[2] -= used
            remaining -= used
        day += timedelta(days=1)
    return result


async def refresh_automatic_plans(db: AsyncSession, now: datetime) -> int:
    """后台每小时刷新所有启用门店，无需浏览器打开；截止时保留最终快照。"""
    from sqlalchemy.dialects.mysql import insert as mysql_insert
    from sqlalchemy.dialects.sqlite import insert as sqlite_insert
    from sqlalchemy.orm import selectinload

    from app.models.category import Category
    from app.models.employee import Employee
    from app.models.enums import EmployeeRole
    from app.models.store import Store, StoreDepartment
    from app.models.supplier_product import SupplierProduct
    from app.services.purchase_plan_submission import plan_cutoff

    pairs = (
        await db.execute(
            select(StoreDepartment.store_id, StoreDepartment.department_id)
            .join(Store, Store.id == StoreDepartment.store_id)
            .where(Store.is_active.is_(True), StoreDepartment.is_active.is_(True))
            .order_by(StoreDepartment.store_id, StoreDepartment.department_id)
        )
    ).all()
    count = 0
    days = [now.date() + timedelta(days=2 + offset) for offset in range(7)]
    for store_id, department_id in pairs:
        actor = await db.scalar(
            select(Employee.id)
            .where(
                Employee.store_id == store_id,
                Employee.is_active.is_(True),
                (Employee.role == EmployeeRole.STORE_MANAGER)
                | (
                    (Employee.role == EmployeeRole.REGULAR_EMPLOYEE)
                    & (Employee.department_id == department_id)
                ),
            )
            .order_by(Employee.id)
            .limit(1)
        )
        if actor is None:
            continue
        catalog = (
            await db.scalars(
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
        ).all()
        catalog = [item for item in catalog if item.supplier.is_active]
        if not catalog:
            continue
        recommendations = await calculate_replenishment(
            store_id, department_id, days, catalog, db, now
        )
        for day in days:
            values = dict(
                store_id=store_id,
                department_id=department_id,
                arrival_date=day,
                quantities={},
                automatic_quantities={},
                updated_by=actor,
            )
            if db.get_bind().dialect.name == "mysql":
                statement = mysql_insert(PurchasePlan).values(**values)
                await db.execute(statement.on_duplicate_key_update(id=PurchasePlan.id))
            else:
                statement_sqlite = sqlite_insert(PurchasePlan).values(**values)
                await db.execute(
                    statement_sqlite.on_conflict_do_nothing(
                        index_elements=["store_id", "department_id", "arrival_date"]
                    )
                )
            plan = await db.scalar(
                select(PurchasePlan)
                .where(
                    PurchasePlan.store_id == store_id,
                    PurchasePlan.department_id == department_id,
                    PurchasePlan.arrival_date == day,
                )
                .with_for_update()
                .execution_options(populate_existing=True)
            )
            assert plan is not None
            if plan.purchase_id is not None:
                continue
            cutoff = plan_cutoff(day)
            if now > cutoff + timedelta(minutes=1) and plan.automatic_quantities:
                continue
            plan.automatic_quantities = {
                str(item.id): recommendations.get(item.id, {})
                .get(day, {})
                .get("suggested_quantity", 0)
                for item in catalog
            }
            count += 1
        await db.commit()
    return count


async def calculate_replenishment(
    store_id: int, department_id: int, days: list[date], catalog, db: AsyncSession, now: datetime
) -> dict:
    today = now.date()
    catalog_ids = [item.id for item in catalog]
    if not catalog_ids:
        return {}
    products = (
        await db.scalars(
            select(Product).where(
                Product.store_id == store_id, Product.supplier_product_id.in_(catalog_ids)
            )
        )
    ).all()
    catalog_by_product = {product.id: product.supplier_product_id for product in products}
    sales_rows = (
        await db.execute(
            select(SaleItem.product_id, func.date(Sale.sold_at), func.sum(SaleItem.quantity))
            .join(Sale, Sale.id == SaleItem.sale_id)
            .where(
                Sale.store_id == store_id,
                Sale.sold_at >= datetime.combine(today - timedelta(days=28), time.min),
                Sale.sold_at < datetime.combine(today, time.min),
                SaleItem.product_id.in_(catalog_by_product),
            )
            .group_by(SaleItem.product_id, func.date(Sale.sold_at))
        )
    ).all()
    totals: dict[tuple[int, int], int] = {}
    for product_id, sold_date, quantity in sales_rows:
        key = (catalog_by_product[product_id], date.fromisoformat(str(sold_date)).weekday())
        totals[key] = totals.get(key, 0) + int(quantity)
    batch_rows = (
        await db.execute(
            select(
                InventoryBatch.product_id,
                InventoryBatch.arrived_at,
                InventoryBatch.expiration_date,
                InventoryBatch.remaining_quantity,
            ).where(
                InventoryBatch.store_id == store_id,
                InventoryBatch.product_id.in_(catalog_by_product),
                InventoryBatch.remaining_quantity > 0,
            )
        )
    ).all()
    stocks: dict[int, list[tuple[date, date | None, int]]] = {}
    for product_id, arrived, expires, quantity in batch_rows:
        stocks.setdefault(catalog_by_product[product_id], []).append(
            (arrived.date(), expires, int(quantity))
        )
    incoming_rows = (
        await db.execute(
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
    ).all()
    incoming: dict[int, list[tuple[date, date | None, int]]] = {}
    for catalog_id, arrival, expires, quantity in incoming_rows:
        # 逾期未签收的单子按今日可补签收到货，避免重复采购。
        incoming.setdefault(catalog_id, []).append(
            (max(today, arrival.date()), expires, int(quantity))
        )
    plans = (
        await db.scalars(
            select(PurchasePlan).where(
                PurchasePlan.store_id == store_id,
                PurchasePlan.department_id == department_id,
                PurchasePlan.arrival_date >= today,
                PurchasePlan.arrival_date <= max(days),
            )
        )
    ).all()
    result: dict[int, dict] = {}
    # 也模拟尚未生成订单的更早计划，避免七天计划逐日重复补同一库存。
    simulation_days = set(days) | {plan.arrival_date for plan in plans if plan.purchase_id is None}
    for item in catalog:
        from app.services.purchase_plan_submission import plan_cutoff

        overrides = {}
        for plan in plans:
            if plan.purchase_id is not None:
                continue
            effective = (
                (plan.automatic_quantities | plan.quantities)
                if now >= plan_cutoff(plan.arrival_date)
                else plan.quantities
            )
            if str(item.id) in effective:
                overrides[plan.arrival_date] = effective[str(item.id)]
        item_days = sorted(
            day
            for day in simulation_days
            if not any(plan.arrival_date == day and plan.purchase_id is not None for plan in plans)
        )
        if not item_days:
            result[item.id] = {}
            continue
        result[item.id] = simulate_replenishment(
            now,
            item_days,
            {weekday: ceil(totals.get((item.id, weekday), 0) / 4) for weekday in range(7)},
            stocks.get(item.id, []),
            incoming.get(item.id, []),
            item.minimum_stock,
            item.shelf_life_days,
            overrides,
        )
    return result
