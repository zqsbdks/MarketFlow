"""按门店销量、批次保质期和已订到货量逐日推演补货。"""

from datetime import date, datetime, time, timedelta
from math import ceil

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import FORECAST_CACHE_NAMESPACE, FORECAST_CACHE_SECONDS, business_cache
from app.crud import replenishment as data_access


@business_cache(FORECAST_CACHE_NAMESPACE, FORECAST_CACHE_SECONDS, shared_forecast=True)
async def weekday_sales_forecast(
    store_id: int, product_ids: tuple[int, ...], today: date, db: AsyncSession
) -> dict[str, list[int]]:
    """统计本店商品最近28个完整日期的同星期销量，返回每周7天的日销量预测。

    product_ids必须是稳定排序的元组，today使用日本业务日期；当天未结束销量不纳入。
    没有销售的星期仍按4周平均，不按有销售的日期数平均，避免夸大稀疏销量。
    预测可按店铺/商品/日期缓存，实际库存与最终建议量不能复用此缓存。"""
    rows = (
        await data_access.get_recent_daily_sales(
            db=db, product_ids=product_ids, store_id=store_id, today=today
        )
    ).all()
    totals_mapping = {}
    for totals_product_id in product_ids:
        totals_mapping[str(totals_product_id)] = [0] * 7
    totals = totals_mapping
    for product_id, sold_date, quantity in rows:
        totals[str(product_id)][date.fromisoformat(str(sold_date)).weekday()] += int(quantity)
    result_mapping = {}
    for result_key, result_values in totals.items():
        result_values_new = []
        for result_quantity in result_values:
            result_values_new.append(ceil(result_quantity / 4))
        result_mapping[result_key] = result_values_new
    return result_mapping


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
    stock_values = []
    for stock_batch in batches:
        stock_values.append(list(stock_batch))
    stock = stock_values  # [可用日期，到期日期，数量]
    result = {}
    first = now.date()
    last = max(days)
    day = first
    while day <= last:
        # 到期日当天仍可销售，日期小于业务日期的批次才从可用库存移除。
        stock_values_new = []
        for stock_batch_item in stock:
            if stock_batch_item[1] is None or stock_batch_item[1] >= day:
                stock_values_new.append(stock_batch_item)
        stock = stock_values_new
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
        stock.sort(key=batch_expiration_sort_key)
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
    from app.services.purchase_plan_submission import plan_cutoff

    pairs = (await data_access.get_enabled_store_departments(db=db)).all()
    count = 0
    days_values = []
    for days_offset in range(7):
        days_values.append(now.date() + timedelta(days=2 + days_offset))
    days = days_values
    for store_id, department_id in pairs:
        actor = await data_access.get_automatic_plan_employee(
            db=db, department_id=department_id, store_id=store_id
        )
        if actor is None:
            continue
        catalog = (
            await data_access.get_automatic_plan_catalog(
                db=db, department_id=department_id, store_id=store_id
            )
        ).all()
        catalog_values = []
        for catalog_item in catalog:
            if catalog_item.supplier.is_active:
                catalog_values.append(catalog_item)
        catalog = catalog_values
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
                await data_access.insert_automatic_plan_mysql(db=db, values=values)
            else:
                await data_access.insert_automatic_plan_sqlite(db=db, values=values)
            plan = await data_access.get_automatic_plan_for_update(
                db=db, day=day, department_id=department_id, store_id=store_id
            )
            assert plan is not None
            if plan.purchase_id is not None:
                continue
            cutoff = plan_cutoff(day)
            if now > cutoff + timedelta(minutes=1) and plan.automatic_quantities:
                continue
            automatic_quantities_mapping = {}
            for automatic_quantities_item in catalog:
                automatic_quantities_mapping[str(automatic_quantities_item.id)] = (
                    recommendations.get(automatic_quantities_item.id, {})
                    .get(day, {})
                    .get("suggested_quantity", 0)
                )
            plan.automatic_quantities = automatic_quantities_mapping
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
    catalog_ids_values = []
    for catalog_ids_item in catalog:
        catalog_ids_values.append(catalog_ids_item.id)
    catalog_ids = catalog_ids_values
    if not catalog_ids:
        return {}
    products = (
        await data_access.get_replenishment_products(
            db=db, catalog_ids=catalog_ids, store_id=store_id
        )
    ).all()
    catalog_by_product_mapping = {}
    for catalog_by_product_product in products:
        catalog_by_product_mapping[catalog_by_product_product.id] = (
            catalog_by_product_product.supplier_product_id
        )
    catalog_by_product = catalog_by_product_mapping
    forecasts = await weekday_sales_forecast(store_id, tuple(sorted(catalog_by_product)), today, db)
    forecast_by_catalog_mapping = {}
    for (
        forecast_by_catalog_product_id,
        forecast_by_catalog_catalog_id,
    ) in catalog_by_product.items():
        forecast_by_catalog_mapping[forecast_by_catalog_catalog_id] = forecasts.get(
            str(forecast_by_catalog_product_id), [0] * 7
        )
    forecast_by_catalog = forecast_by_catalog_mapping
    batch_rows = (
        await data_access.get_replenishment_batches(
            db=db, catalog_by_product=catalog_by_product, store_id=store_id
        )
    ).all()
    stocks: dict[int, list[tuple[date, date | None, int]]] = {}
    for product_id, arrived, expires, quantity in batch_rows:
        stocks.setdefault(catalog_by_product[product_id], []).append(
            (arrived.date(), expires, int(quantity))
        )
    incoming_rows = (
        await data_access.get_pending_arrival_items(
            db=db, catalog_ids=catalog_ids, days=days, store_id=store_id
        )
    ).all()
    incoming: dict[int, list[tuple[date, date | None, int]]] = {}
    for catalog_id, arrival, expires, quantity in incoming_rows:
        # 逾期未签收的单子按今日可补签收到货，避免重复采购。
        incoming.setdefault(catalog_id, []).append(
            (max(today, arrival.date()), expires, int(quantity))
        )
    plans = (
        await data_access.get_replenishment_plans(
            db=db, days=days, department_id=department_id, store_id=store_id, today=today
        )
    ).all()
    result: dict[int, dict] = {}
    # 也模拟尚未生成订单的更早计划，避免七天计划逐日重复补同一库存。
    response_items_set = set()
    for response_items_plan in plans:
        if response_items_plan.purchase_id is None:
            response_items_set.add(response_items_plan.arrival_date)
    response_items = response_items_set
    simulation_days = set(days) | response_items
    for item in catalog:
        from app.services.purchase_plan_submission import plan_cutoff

        overrides = {}
        for plan in plans:
            if plan.purchase_id is not None:
                continue
            if now >= plan_cutoff(plan.arrival_date):
                effective = plan.automatic_quantities | plan.quantities
            else:
                effective = plan.quantities
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
        response_mapping_mapping = {}
        for response_mapping_weekday in range(7):
            response_mapping_mapping[response_mapping_weekday] = forecast_by_catalog.get(
                item.id, [0] * 7
            )[response_mapping_weekday]
        response_mapping = response_mapping_mapping
        result[item.id] = simulate_replenishment(
            now,
            item_days,
            response_mapping,
            stocks.get(item.id, []),
            incoming.get(item.id, []),
            item.minimum_stock,
            item.shelf_life_days,
            overrides,
        )
    return result


def batch_expiration_sort_key(batch):
    """按到期日期排序；没有到期日期的批次放在最后。"""
    expiration_date = batch[1]
    if expiration_date is None:
        return date.max
    return expiration_date
