"""保存截止前的订货量，以及锁定计划并生成唯一进货单。"""

from datetime import date, datetime, time, timedelta
from uuid import NAMESPACE_URL, uuid5

from fastapi import HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.business_time import business_now
from app.crud import purchase_plan_submission as data_access
from app.crud.auth import get_employee_by_id
from app.crud.operation_audit_logs import create_operation_audit_log
from app.crud.scheduler import get_due_plan_ids
from app.crud.stores import first_active_store_id, get_store_by_id
from app.models.enums import EmployeeRole
from app.schemas.purchase_plan import SaveMinimumStock, SavePurchasePlan
from app.schemas.purchases_requests import CreatePurchaseRequest
from app.services.purchases import create_purchase_records as create_purchase
from app.services.quantity_confirmation import check_confirmation
from app.services.replenishment import calculate_replenishment, weekday_sales_forecast


def plan_cutoff(arrival: date) -> datetime:
    return datetime.combine(arrival - timedelta(days=2), time(hour=12))


async def validate_plan_writer(request, actor_id: int, db: AsyncSession):
    """重新校验账号、所属门店、部门及有效供应目录，返回可修改的目录项。

    读店与写店必须都等于员工所属门店；店长可跨部门，正式员工仅本部门。
    总部及契约工无此写权限，停用账号和未修改初始密码的账号也不能操作。
    该函数不提交事务，权限检查不能被前端按钮状态或缓存结果代替。"""
    employee = await data_access.get_plan_writer(db=db, actor_id=actor_id)
    store_id = db.info.get("write_store_id")
    if (
        employee is None
        or not employee.is_active
        or employee.must_change_password
        or employee.role not in (EmployeeRole.STORE_MANAGER, EmployeeRole.REGULAR_EMPLOYEE)
        or employee.store_id != store_id
        or db.info.get("read_store_id") != store_id
        or (
            employee.role == EmployeeRole.REGULAR_EMPLOYEE
            and employee.department_id != request.department_id
        )
    ):
        raise HTTPException(403, "只有本店店长或所属部门正式员工可以修改订货计划")
    enabled = await data_access.get_plan_department_enabled(
        db=db, request=request, store_id=store_id
    )
    catalog = await data_access.get_writable_catalog_product(
        db=db, request=request, store_id=store_id
    )
    if not enabled or catalog is None or not catalog.is_active or not catalog.supplier.is_active:
        raise HTTPException(400, "本店部门或供应商商品未启用")
    if catalog.shelf_life_days is None:
        raise HTTPException(400, "供应商商品未设置默认保质期")
    return catalog


async def save_minimum_stock(
    request: SaveMinimumStock,
    actor_id: int,
    db: AsyncSession,
    *,
    http_request: Request | None = None,
    access_employee_id: int | None = None,
) -> dict:
    """锁定本店供应目录并保存保底库存，必要时先返回异常数量确认挑战。

    保底值表示预测销售后的目标余量，不是最小下单量。异常首次请求saved=false，
    此时不更改目录；确认后的数量变更与操作审计在本函数内一起提交。
    确认签名绑定员工及具体数量，不能将其他商品的确认凭据用于本商品。"""
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
            selected_store_id = None
        elif raw_store_id:
            try:
                selected_store_id = int(raw_store_id)
            except ValueError as error:
                raise HTTPException(422, "门店ID无效") from error
            if selected_store_id <= 0:
                raise HTTPException(422, "门店ID无效")
        if selected_store_id is None and is_headquarters and (raw_store_id != "all"):
            selected_store_id = await first_active_store_id(db)
        if selected_store_id is not None:
            selected_store = await get_store_by_id(selected_store_id, db)
            if selected_store is None or not selected_store.is_active:
                raise HTTPException(403, "门店不存在或已停用")
        if not is_headquarters and access_employee.store_id is None:
            raise HTTPException(403, "员工尚未分配门店")
        if is_headquarters:
            raise HTTPException(403, "总部不执行门店日常业务")
        if selected_store_id != access_employee.store_id:
            raise HTTPException(403, "跨店查看为只读，不能修改其他门店")
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
    catalog = await validate_plan_writer(request, actor_id, db)
    await db.refresh(catalog, with_for_update=True)
    before = catalog.minimum_stock
    product_ids = tuple((await data_access.get_catalog_product_ids(db=db, catalog=catalog)).all())
    forecast = await weekday_sales_forecast(
        catalog.store_id, product_ids, business_now().date(), db
    )
    reference = max([before, *(max(values) for values in forecast.values())])
    confirmation = check_confirmation(
        request, actor_id, catalog.store_id, "minimum", reference, before
    )
    if confirmation and confirmation.get("confirmation_required"):
        return confirmation
    catalog.minimum_stock = request.minimum_stock
    await create_operation_audit_log(
        employee_id=actor_id,
        module="purchase",
        action="minimum_stock",
        target_type="supplier_product",
        target_id=catalog.id,
        before_data={"minimum_stock": before},
        after_data={"minimum_stock": catalog.minimum_stock, "confirmation": confirmation},
        reason=None,
        db=db,
    )
    await db.commit()
    return {"minimum_stock": catalog.minimum_stock}


async def save_purchase_plan(
    request: SavePurchasePlan,
    actor_id: int,
    db: AsyncSession,
    *,
    http_request: Request | None = None,
    access_employee_id: int | None = None,
) -> dict:
    """在到货日前两天12:00截止前保存单个商品的人工订货总量。

    quantity=0表示人工取消该日订货，None表示移除覆盖、恢复自动计算。
    先原子创建计划头，再获取行锁并重新检查截止时间，避免首次并发创建和越线保存。
    异常输入只返回确认挑战，不写入数量；成功时保存人工覆盖与审计并提交。
    后台automatic_quantities不被此操作覆盖，相同格子的15改25是替换而不是相加。"""
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
            selected_store_id = None
        elif raw_store_id:
            try:
                selected_store_id = int(raw_store_id)
            except ValueError as error:
                raise HTTPException(422, "门店ID无效") from error
            if selected_store_id <= 0:
                raise HTTPException(422, "门店ID无效")
        if selected_store_id is None and is_headquarters and (raw_store_id != "all"):
            selected_store_id = await first_active_store_id(db)
        if selected_store_id is not None:
            selected_store = await get_store_by_id(selected_store_id, db)
            if selected_store is None or not selected_store.is_active:
                raise HTTPException(403, "门店不存在或已停用")
        if not is_headquarters and access_employee.store_id is None:
            raise HTTPException(403, "员工尚未分配门店")
        if is_headquarters:
            raise HTTPException(403, "总部不执行门店日常业务")
        if selected_store_id != access_employee.store_id:
            raise HTTPException(403, "跨店查看为只读，不能修改其他门店")
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
    catalog = await validate_plan_writer(request, actor_id, db)
    store_id = db.info.get("write_store_id")
    now = business_now()
    if now >= plan_cutoff(request.arrival_date):
        raise HTTPException(400, "该到货日已截止，订货计划不可修改")
    if request.arrival_date > now.date() + timedelta(days=30):
        raise HTTPException(400, "预计到货日期须在今天至30天内")
    values = dict(
        store_id=store_id,
        department_id=request.department_id,
        arrival_date=request.arrival_date,
        quantities={},
        automatic_quantities={},
        updated_by=actor_id,
    )
    if db.get_bind().dialect.name == "mysql":
        await data_access.insert_plan_if_missing_mysql(db=db, values=values)
    else:
        await data_access.insert_plan_if_missing_sqlite(db=db, values=values)
    plan = await data_access.get_plan_for_update(db=db, request=request, store_id=store_id)
    assert plan is not None
    if business_now() >= plan_cutoff(request.arrival_date) or plan.purchase_id is not None:
        raise HTTPException(400, "该到货日已截止，订货计划不可修改")
    before = dict(plan.quantities)
    recommendations = await calculate_replenishment(
        store_id, request.department_id, [request.arrival_date], [catalog], db, business_now()
    )
    recommendation = recommendations.get(catalog.id, {}).get(request.arrival_date, {})
    previous = (plan.automatic_quantities | before).get(str(catalog.id), 0)
    reference = max(
        recommendation.get("suggested_quantity", 0),
        recommendation.get("forecast_sales", 0),
        catalog.minimum_stock,
    )
    confirmation = check_confirmation(request, actor_id, store_id, "order", reference, previous)
    if confirmation and confirmation.get("confirmation_required"):
        return confirmation
    quantities = dict(before)
    if business_now() >= plan_cutoff(request.arrival_date):
        raise HTTPException(400, "该到货日已截止，订货计划不可修改")
    if request.quantity is None:
        quantities.pop(str(request.supplier_product_id), None)
    else:
        quantities[str(request.supplier_product_id)] = request.quantity
    plan.quantities = quantities
    plan.updated_by = actor_id
    await db.flush()
    await create_operation_audit_log(
        employee_id=actor_id,
        module="purchase",
        action="save_plan",
        target_type="purchase_plan",
        target_id=plan.id,
        before_data={"quantities": before},
        after_data={
            "quantities": quantities,
            "arrival_date": plan.arrival_date,
            "confirmation": confirmation,
        },
        reason=None,
        db=db,
    )
    await db.commit()
    return {"quantity": request.quantity, "arrival_date": request.arrival_date}


async def submit_due_plan(plan_id: int, db: AsyncSession, now: datetime | None = None) -> bool:
    """锁定到期计划并生成一次进货单，返回本次是否创建订单。

    自动量与人工覆盖合并时以人工为准，0不进入明细，空计划暂不生成订单。
    固定请求ID及purchase_id标记防止重复调度重复生成；补处理保留原截止时间。
    本函数不commit，调用调度器必须把订单、计划标记和审计放在同一事务提交。
    自动建议橘红标记只属于界面提示，不过滤明细，也不等待人工确认。"""
    now = now or business_now()
    plan = await data_access.get_submission_plan_for_update(db=db, plan_id=plan_id)
    if plan is None or plan.purchase_id is not None or now < plan_cutoff(plan.arrival_date):
        return False
    items_values = []
    for items_key, items_value in (plan.automatic_quantities | plan.quantities).items():
        if items_value > 0:
            items_values.append({"supplier_product_id": int(items_key), "quantity": items_value})
    items = items_values
    if not items:
        return False
    db.info["write_store_id"] = plan.store_id
    request = CreatePurchaseRequest(
        department_id=plan.department_id,
        expected_arrival_date=plan.arrival_date,
        client_request_id=uuid5(NAMESPACE_URL, f"marketflow:purchase-plan:{plan.id}"),
        items=items,
    )
    # 补处理仍保留原本中午的下单时间，确保到货时间晚于下单时间。
    purchase = await create_purchase(
        request, plan.updated_by, db, ordered_at_override=plan_cutoff(plan.arrival_date)
    )
    plan.purchase_id = purchase.id
    await create_operation_audit_log(
        employee_id=None,
        module="purchase",
        action="auto_submit",
        target_type="purchase",
        target_id=purchase.id,
        before_data=None,
        after_data={"plan_id": plan.id, "purchase_no": purchase.purchase_no, "items": items},
        reason="订货截止后自动生成",
        db=db,
        store_id=plan.store_id,
    )
    return True


async def get_due_plan_ids_service(latest_arrival_date, db):
    """只挑出候选计划；真正提交时还会持有行锁并再次核对截止时间。"""
    return await get_due_plan_ids(latest_arrival_date, db)
