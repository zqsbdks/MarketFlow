"""进货计划表：未来七天已有到货安排与上周同曜日销售参考。"""

from datetime import date, datetime, time, timedelta

from fastapi import HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.business_time import business_now
from app.crud import purchase_planning as data_access
from app.crud.auth import get_employee_by_id
from app.crud.stores import first_active_store_id, get_store_by_id
from app.models.enums import EmployeeRole
from app.services.purchase_plan_submission import plan_cutoff
from app.services.replenishment import calculate_replenishment


# region 组装七天计划表
async def get_purchase_planning(
    department_id: int,
    arrival_date: date | None,
    db: AsyncSession,
    *,
    http_request: Request | None = None,
    access_employee_id: int | None = None,
) -> dict:
    """每种供应商品一行，组合自动建议、人工覆盖、已有到货及历史销量。

    默认从今天+2天展示7个到货日，额外提供前一天到货参考列。
    截止或已下单日期显示持久化快照，可编辑日期重新推演；GET不保存或生成订单。
    门店读取范围由上层依赖配置，跨店查看不具备写入权限。
    """

    # 本接口在服务层明确检查店铺范围；不依赖数据库自动事件。
    if http_request is not None:
        if access_employee_id is None:
            raise HTTPException(401, "缺少当前员工身份")
        access_employee = await get_employee_by_id(employee_id=access_employee_id, db=db)
        if access_employee is None or not access_employee.is_active:
            raise HTTPException(401, "账号不存在或已停用")
        is_headquarters = access_employee.role == EmployeeRole.HEADQUARTERS
        selected_store_id = access_employee.store_id
        raw_store_id = http_request.headers.get("X-Store-ID")
        if not raw_store_id:
            raw_store_id = http_request.query_params.get("store_id")
        if raw_store_id == "all":
            raise HTTPException(403, "此接口不支持全公司汇总")
        elif raw_store_id:
            try:
                selected_store_id = int(raw_store_id)
            except ValueError as error:
                raise HTTPException(422, "门店ID无效") from error
            if selected_store_id <= 0:
                raise HTTPException(422, "门店ID无效")
        if selected_store_id is None and is_headquarters and raw_store_id != "all":
            selected_store_id = await first_active_store_id(db)
        if selected_store_id is not None:
            selected_store = await get_store_by_id(selected_store_id, db)
            if selected_store is None or not selected_store.is_active:
                raise HTTPException(403, "门店不存在或已停用")
        if not is_headquarters and access_employee.store_id is None:
            raise HTTPException(403, "员工尚未分配门店")

        # 这里只记录本次查询参数；CRUD 会明确读取并添加 store_id 条件。
        db.info.update(
            actor_id=access_employee.id,
            actor_role=access_employee.role,
            own_store_id=access_employee.store_id,
            read_store_id=selected_store_id,
            write_store_id=access_employee.store_id,
            company_management=False,
            company_catalog_read=False,
            private_employee_path=False,
            store_context=True,
        )
        http_request.state.store_id = selected_store_id
        http_request.state.employee_id = access_employee.id
        http_request.state.own_store_id = access_employee.store_id

    today = business_now().date()
    first_day = arrival_date or today + timedelta(days=2)
    if not today <= first_day <= today + timedelta(days=30):
        raise HTTPException(400, "预计到货日期须在今天至30天内")
    store_id = db.info.get("read_store_id")
    if store_id is None:
        raise HTTPException(400, "请先选择门店")
    days_values = []
    for days_offset in range(7):
        days_values.append(first_day + timedelta(days=days_offset))
    days = days_values
    previous_arrival_date = first_day - timedelta(days=1)
    plans = (
        await data_access.get_visible_purchase_plans(
            db=db, days=days, department_id=department_id, store_id=store_id
        )
    ).all()
    planned_mapping = {}
    for planned_plan in plans:
        planned_mapping[planned_plan.arrival_date] = planned_plan
    planned = planned_mapping
    day_keys_set = set()
    for day_keys_day in days:
        day_keys_set.add(day_keys_day.isoformat())
    day_keys = day_keys_set
    day_keys.add(previous_arrival_date.isoformat())
    range_start = datetime.combine(previous_arrival_date, time.min)
    range_end = datetime.combine(days[-1] + timedelta(days=1), time.min)
    catalog = (await data_access.get_department_catalog(db=db, department_id=department_id)).all()
    catalog_values = []
    for catalog_item_item in catalog:
        if catalog_item_item.supplier is not None and catalog_item_item.supplier.is_active:
            catalog_values.append(catalog_item_item)
    catalog = catalog_values
    if not catalog:
        return {
            "arrival_date": first_day,
            "previous_arrival_date": previous_arrival_date,
            "days": days,
            "items": [],
        }
    catalog_ids_values = []
    for catalog_ids_item in catalog:
        catalog_ids_values.append(catalog_ids_item.id)
    catalog_ids = catalog_ids_values
    recommendations = await calculate_replenishment(
        store_id, department_id, days, catalog, db, business_now()
    )
    products = (
        await data_access.get_catalog_products(db=db, catalog_ids=catalog_ids, store_id=store_id)
    ).all()
    by_catalog_mapping = {}
    for by_catalog_item in products:
        by_catalog_mapping[by_catalog_item.supplier_product_id] = by_catalog_item
    by_catalog = by_catalog_mapping
    product_ids_values = []
    for product_ids_item in products:
        product_ids_values.append(product_ids_item.id)
    product_ids = product_ids_values
    warning_days_mapping = {}
    for warning_days_item in products:
        warning_days_mapping[warning_days_item.id] = warning_days_item.expiry_warning_days
    warning_days = warning_days_mapping

    # 已有进货单按“预计到货日”累计，已签收的用实际到货日累计。
    arrival_rows = (
        await data_access.get_scheduled_arrivals(
            db=db,
            catalog_ids=catalog_ids,
            range_end=range_end,
            range_start=range_start,
            store_id=store_id,
        )
    ).all()
    arrivals: dict[tuple[int, str], dict[str, int]] = {}
    for catalog_id, status, expected, actual, quantity in arrival_rows:
        if status == "arrived" and actual:
            selected_value = actual
        else:
            selected_value = expected
        arrival_day_key = str(selected_value)
        if arrival_day_key not in day_keys:
            continue
        bucket = arrivals.setdefault((catalog_id, arrival_day_key), {"expected": 0, "received": 0})
        if status == "arrived":
            selected_text = "received"
        else:
            selected_text = "expected"
        bucket[selected_text] += int(quantity)

    sold: dict[tuple[int, str], int] = {}
    stock: dict[int, int] = {}
    expiring: dict[int, int] = {}
    if product_ids:
        sold_rows = (
            await data_access.get_last_week_sales(
                db=db, first_day=first_day, product_ids=product_ids, store_id=store_id
            )
        ).all()
        for product_id, sold_day, quantity in sold_rows:
            sold[(product_id, str(sold_day))] = int(quantity)
        batch_rows = (
            await data_access.get_saleable_batch_stock(
                db=db, product_ids=product_ids, store_id=store_id
            )
        ).all()
        for product_id, expires, quantity in batch_rows:
            if expires is None or expires >= today:
                stock[product_id] = stock.get(product_id, 0) + quantity
                product_warning_days = warning_days[product_id]
                if (
                    expires is not None
                    and product_warning_days is not None
                    and expires <= today + timedelta(days=product_warning_days)
                ):
                    expiring[product_id] = expiring.get(product_id, 0) + quantity

    items = []
    for catalog_item in catalog:
        product = by_catalog.get(catalog_item.id)
        if product:
            product_id = product.id
        else:
            product_id = None
        daily = []
        for day in days:
            arrival = arrivals.get((catalog_item.id, day.isoformat()), {})
            recommendation = recommendations.get(catalog_item.id, {}).get(day, {})
            stored = planned.get(day)
            quantity = recommendation.get("planned_quantity", 0)
            if stored is not None and (
                stored.purchase_id is not None or business_now() >= plan_cutoff(day)
            ):
                quantity = (stored.automatic_quantities | stored.quantities).get(
                    str(catalog_item.id), 0
                )
            if product_id is not None:
                last_week_sales_value = sold.get(
                    (product_id, (day - timedelta(days=7)).isoformat()), 0
                )
            else:
                last_week_sales_value = 0
            daily.append(
                {
                    "date": day,
                    "planned_quantity": quantity,
                    "suggested_quantity": recommendation.get("suggested_quantity", 0),
                    "is_manual": stored is not None and str(catalog_item.id) in stored.quantities,
                    "forecast_sales": recommendation.get("forecast_sales", 0),
                    "expected_quantity": arrival.get("expected", 0),
                    "received_quantity": arrival.get("received", 0),
                    "last_week_sales": last_week_sales_value,
                }
            )
        if product_id is not None:
            saleable_stock_value = stock.get(product_id, 0)
        else:
            saleable_stock_value = 0
        if product_id is not None:
            near_expiry_stock_quantity_value = expiring.get(product_id, 0)
        else:
            near_expiry_stock_quantity_value = 0
        items.append(
            {
                "previous_expected_quantity": arrivals.get(
                    (catalog_item.id, previous_arrival_date.isoformat()), {}
                ).get("expected", 0),
                "previous_received_quantity": arrivals.get(
                    (catalog_item.id, previous_arrival_date.isoformat()), {}
                ).get("received", 0),
                "supplier_product_id": catalog_item.id,
                "minimum_stock": catalog_item.minimum_stock,
                "product_id": product_id,
                "name": catalog_item.name,
                "supplier_name": catalog_item.supplier.name,
                "unit_cost": catalog_item.unit_cost,
                "saleable_stock": saleable_stock_value,
                "near_expiry_stock_quantity": near_expiry_stock_quantity_value,
                "days": daily,
            }
        )
    return {
        "arrival_date": first_day,
        "previous_arrival_date": previous_arrival_date,
        "days": days,
        "items": items,
    }


# endregion


__all__ = ["get_purchase_planning"]
