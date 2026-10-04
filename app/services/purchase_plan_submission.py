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
from app.models.purchase_plan import PurchasePlan
from app.models.store import StoreDepartment
from app.models.supplier_product import SupplierProduct
from app.schemas.purchase_plan import SaveMinimumStock, SavePurchasePlan
from app.schemas.purchases_requests import CreatePurchaseRequest


def plan_cutoff(arrival: date) -> datetime:
    return datetime.combine(arrival - timedelta(days=2), time(hour=12))


async def validate_plan_writer(request, actor_id: int, db: AsyncSession):
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
    catalog = await validate_plan_writer(request, actor_id, db)
    await db.refresh(catalog, with_for_update=True)
    before = catalog.minimum_stock
    catalog.minimum_stock = request.minimum_stock
    await create_operation_audit_log(
        employee_id=actor_id,
        module="purchase",
        action="minimum_stock",
        target_type="supplier_product",
        target_id=catalog.id,
        before_data={"minimum_stock": before},
        after_data={"minimum_stock": catalog.minimum_stock},
        reason=None,
        db=db,
    )
    await db.commit()
    return {"minimum_stock": catalog.minimum_stock}


async def save_purchase_plan(request: SavePurchasePlan, actor_id: int, db: AsyncSession) -> dict:
    await validate_plan_writer(request, actor_id, db)
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
    quantities = dict(before)
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
        after_data={"quantities": quantities, "arrival_date": plan.arrival_date},
        reason=None,
        db=db,
    )
    await db.commit()
    return {"quantity": request.quantity, "arrival_date": request.arrival_date}


async def submit_due_plan(plan_id: int, db: AsyncSession, now: datetime | None = None) -> bool:
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
