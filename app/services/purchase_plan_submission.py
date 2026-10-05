"""保存截止前的订货量，以及锁定计划并生成唯一进货单。"""

from datetime import date, datetime, time, timedelta
from uuid import NAMESPACE_URL, uuid5

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.dialects.mysql import insert as mysql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.business_time import business_now
from app.crud.operation_audit_logs import create_operation_audit_log
from app.crud.purchases import create_purchase
from app.models.category import Category
from app.models.employee import Employee
from app.models.enums import EmployeeRole
from app.models.product import Product
from app.models.purchase_plan import PurchasePlan
from app.models.store import StoreDepartment
from app.models.supplier_product import SupplierProduct
from app.schemas.purchase_plan import SaveMinimumStock, SavePurchasePlan
from app.schemas.purchases_requests import CreatePurchaseRequest
from app.services.quantity_confirmation import check_confirmation
from app.services.replenishment import calculate_replenishment, weekday_sales_forecast


def plan_cutoff(arrival: date) -> datetime:
    return datetime.combine(arrival - timedelta(days=2), time(hour=12))


async def validate_plan_writer(request, actor_id: int, db: AsyncSession):
    """重新校验账号、所属门店、部门及有效供应目录，返回可修改的目录项。

    读店与写店必须都等于员工所属门店；店长可跨部门，正式员工仅本部门。
    总部及契约工无此写权限，停用账号和未修改初始密码的账号也不能操作。
    该函数不提交事务，权限检查不能被前端按钮状态或缓存结果代替。"""
    employee = await db.get(Employee, actor_id)
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
    enabled = await db.scalar(
        select(StoreDepartment.is_active).where(
            StoreDepartment.store_id == store_id,
            StoreDepartment.department_id == request.department_id,
        )
    )
    catalog = await db.scalar(
        select(SupplierProduct)
        .join(Category)
        .options(
            selectinload(SupplierProduct.supplier),
        )
        .where(
            SupplierProduct.id == request.supplier_product_id,
            SupplierProduct.store_id == store_id,
            Category.department_id == request.department_id,
        )
    )
    if not enabled or catalog is None or not catalog.is_active or not catalog.supplier.is_active:
        raise HTTPException(400, "本店部门或供应商商品未启用")
    if catalog.shelf_life_days is None:
        raise HTTPException(400, "供应商商品未设置默认保质期")
    return catalog


async def save_minimum_stock(request: SaveMinimumStock, actor_id: int, db: AsyncSession) -> dict:
    """锁定本店供应目录并保存保底库存，必要时先返回异常数量确认挑战。

    保底值表示预测销售后的目标余量，不是最小下单量。异常首次请求saved=false，
    此时不更改目录；确认后的数量变更与操作审计在本函数内一起提交。
    确认签名绑定员工及具体数量，不能将其他商品的确认凭据用于本商品。"""
    catalog = await validate_plan_writer(request, actor_id, db)
    await db.refresh(catalog, with_for_update=True)
    before = catalog.minimum_stock
    product_ids = tuple(
        (
            await db.scalars(
                select(Product.id).where(
                    Product.store_id == catalog.store_id, Product.supplier_product_id == catalog.id
                )
            )
        ).all()
    )
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


async def save_purchase_plan(request: SavePurchasePlan, actor_id: int, db: AsyncSession) -> dict:
    """在到货日前两天12:00截止前保存单个商品的人工订货总量。

    quantity=0表示人工取消该日订货，None表示移除覆盖、恢复自动计算。
    先原子创建计划头，再获取行锁并重新检查截止时间，避免首次并发创建和越线保存。
    异常输入只返回确认挑战，不写入数量；成功时保存人工覆盖与审计并提交。
    后台automatic_quantities不被此操作覆盖，相同格子的15改25是替换而不是相加。"""
    catalog = await validate_plan_writer(request, actor_id, db)
    store_id = db.info.get("write_store_id")
    now = business_now()
    if now >= plan_cutoff(request.arrival_date):
        raise HTTPException(400, "该到货日已截止，订货计划不可修改")
    if request.arrival_date > now.date() + timedelta(days=30):
        raise HTTPException(400, "预计到货日期须在今天至30天内")
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
    values = dict(
        store_id=store_id,
        department_id=request.department_id,
        arrival_date=request.arrival_date,
        quantities={},
        automatic_quantities={},
        updated_by=actor_id,
    )
    # 先原子创建空计划，再加行锁，避免首次并发保存的空行间隙锁死锁。
    if db.get_bind().dialect.name == "mysql":
        insert = mysql_insert(PurchasePlan).values(**values)
        await db.execute(insert.on_duplicate_key_update(id=PurchasePlan.id))
    else:
        insert_sqlite = sqlite_insert(PurchasePlan).values(**values)
        await db.execute(
            insert_sqlite.on_conflict_do_nothing(
                index_elements=["store_id", "department_id", "arrival_date"]
            )
        )
    plan = await db.scalar(statement)
    assert plan is not None
    # 获取锁后重新检查时间，不能让等待中的请求越过截止线。
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
    plan = await db.scalar(
        select(PurchasePlan)
        .where(PurchasePlan.id == plan_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if plan is None or plan.purchase_id is not None or now < plan_cutoff(plan.arrival_date):
        return False
    items = [
        {"supplier_product_id": int(key), "quantity": value}
        for key, value in (plan.automatic_quantities | plan.quantities).items()
        if value > 0
    ]
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
