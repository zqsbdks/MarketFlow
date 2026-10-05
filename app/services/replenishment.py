"""按门店销量、批次保质期和已订到货量逐日推演补货。"""

from datetime import date, datetime, time, timedelta
from math import ceil

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import FORECAST_CACHE_NAMESPACE, FORECAST_CACHE_SECONDS, business_cache
from app.models.inventory_batch import InventoryBatch
from app.models.product import Product
from app.models.purchase import Purchase
from app.models.purchase_item import PurchaseItem
from app.models.purchase_plan import PurchasePlan
from app.models.sale import Sale
from app.models.sale_item import SaleItem


@business_cache(FORECAST_CACHE_NAMESPACE, FORECAST_CACHE_SECONDS, shared_forecast=True)
async def weekday_sales_forecast(
    store_id: int, product_ids: tuple[int, ...], today: date, db: AsyncSession
) -> dict[str, list[int]]:
    """统计本店商品最近28个完整日期的同星期销量，返回每周7天的日销量预测。

    product_ids必须是稳定排序的元组，today使用日本业务日期；当天未结束销量不纳入。
    没有销售的星期仍按4周平均，不按有销售的日期数平均，避免夸大稀疏销量。
    预测可按店铺/商品/日期缓存，实际库存与最终建议量不能复用此缓存。"""
    rows = (
        await db.execute(
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
    ).all()
    totals = {str(product_id): [0] * 7 for product_id in product_ids}
    for product_id, sold_date, quantity in rows:
        totals[str(product_id)][date.fromisoformat(str(sold_date)).weekday()] += int(quantity)
    return {key: [ceil(quantity / 4) for quantity in values] for key, values in totals.items()}


def simulate_replenishment(
    now, days, sales, batches, incoming, minimum_stock, shelf_life, overrides
):
    """纯内存逐日推演：过期清理→已有到货→建议补货→预计销售扣减。

    batches为(可用日期,到期日期,数量)，incoming为(到货日期,到期日期,数量)。
    sales按星期几0至6索引，overrides按到货日保存人工量，0也必须优先。
    保底是销售后的目标余量，并非最低订货量；每天只补一天预计需求。
    当天销量按09:00至21:00剩余时长折算；按天计入到货，不保证每小时都有库存。
    不修改传入批次对象，不执行数据库操作。
    """
    stock = [list(batch) for batch in batches]  # [可用日期，到期日期，数量]
    result = {}
    first = now.date()
    last = max(days)
    day = first
    while day <= last:
        # 到期日当天仍可销售，日期小于业务日期的批次才从可用库存移除。
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
            # 可用库存补到预测销量+保底；人工量覆盖系统建议，包括明确填0。
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
    """按启用门店/部门保存七天自动量，保留人工覆盖与截止快照。

    目录和供应商必须有效，且已设置保质期。本店有效店长/正式员工记录订单归属。
    系统刷新不要求员工已改初始密码，员工前端写入仍要求改密。
    每部门独立提交；已生成订单或已锁定快照不覆盖，浏览器无需打开。
    返回更新的计划头数，不是新生成的订单数。
    """
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
    """实时组装库存、在途订单及人工覆盖，逐日模拟每个供应商品的订货建议。

    返回目录ID到日期到建议详情的嵌套字典。days表示到货日，now是日本业务时间。
    历史销量通过预测缓存复用；批次、待到货和计划每次查询，包含更早计划的影响。
    只读取数据，不保存建议，也不生成订单；实际持久化由refresh_automatic_plans负责。"""
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
    forecasts = await weekday_sales_forecast(store_id, tuple(sorted(catalog_by_product)), today, db)
    forecast_by_catalog = {
        catalog_id: forecasts.get(str(product_id), [0] * 7)
        for product_id, catalog_id in catalog_by_product.items()
    }
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
            {weekday: forecast_by_catalog.get(item.id, [0] * 7)[weekday] for weekday in range(7)},
            stocks.get(item.id, []),
            incoming.get(item.id, []),
            item.minimum_stock,
            item.shelf_life_days,
            overrides,
        )
    return result
