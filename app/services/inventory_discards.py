"""废弃计划、原子库存扣减、不可变损耗记录及自动过期处理。"""

from datetime import date, datetime, time, timedelta
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import lazyload, selectinload
from sqlalchemy.orm.attributes import set_committed_value

from app.core.business_time import business_now
from app.crud.auth import get_employee_by_id
from app.crud.operation_audit_logs import create_operation_audit_log
from app.models.employee import Employee
from app.models.enums import EmployeeRole, InventoryBatchStatus
from app.models.inventory_batch import InventoryBatch
from app.models.inventory_discard import InventoryDiscard, InventoryDiscardItem
from app.models.product import Product
from app.models.store import StoreDepartment
from app.schemas.inventory_discards import (
    DiscardBatchResponse,
    DiscardCreateRequest,
    DiscardItemResponse,
    DiscardListRequest,
    DiscardListResponse,
    DiscardPlanRequest,
    DiscardPlanResponse,
    DiscardResponse,
    DiscardStockResponse,
)


async def validate_actor(employee_id: int, db: AsyncSession, *, write: bool = False) -> Employee:
    employee = await get_employee_by_id(employee_id=employee_id, db=db)
    if employee is None:
        raise HTTPException(401, "当前登录员工不存在")
    if not employee.is_active:
        raise HTTPException(403, "当前账号已停用")
    if employee.must_change_password:
        raise HTTPException(403, "请先修改初始密码")
    if write:
        if employee.role not in (EmployeeRole.STORE_MANAGER, EmployeeRole.REGULAR_EMPLOYEE):
            raise HTTPException(403, "只有店长或正式员工可以手动废弃商品")
        if db.info.get("store_context") and db.info.get("read_store_id") != employee.store_id:
            raise HTTPException(403, "跨店查看为只读，不能修改其他门店")
    return employee


async def load_product(
    product_id: int, employee: Employee, db: AsyncSession, *, lock: bool = False
) -> Product:
    statement = (
        select(Product).where(Product.id == product_id).options(selectinload(Product.department))
    )
    if lock:
        statement = statement.with_for_update().execution_options(populate_existing=True)
    product = await db.scalar(statement)
    if product is None:
        raise HTTPException(404, "商品不存在")
    if product.store_id != employee.store_id:
        raise HTTPException(403, "只能废弃所属门店的商品")
    if (
        employee.role == EmployeeRole.REGULAR_EMPLOYEE
        and employee.department_id != product.department_id
    ):
        raise HTTPException(403, "正式员工只能废弃自己所属部门的商品")
    enabled = await db.scalar(
        select(StoreDepartment.is_active).where(
            StoreDepartment.store_id == product.store_id,
            StoreDepartment.department_id == product.department_id,
        )
    )
    if not enabled or product.department is None:
        raise HTTPException(400, "本店未启用此部门")
    return product


async def eligible_batches(
    product: Product, db: AsyncSession, *, lock: bool = False
) -> list[InventoryBatch]:
    now = business_now()
    statement = (
        select(InventoryBatch)
        .where(
            InventoryBatch.store_id == product.store_id,
            InventoryBatch.product_id == product.id,
            InventoryBatch.remaining_quantity > 0,
            InventoryBatch.arrived_at <= now,
            or_(
                InventoryBatch.expiration_date.is_(None),
                InventoryBatch.expiration_date >= now.date(),
            ),
        )
        .options(selectinload(InventoryBatch.purchase_item))
        .order_by(
            InventoryBatch.expiration_date.is_(None),
            InventoryBatch.expiration_date,
            InventoryBatch.arrived_at,
            InventoryBatch.id,
        )
    )
    if lock:
        statement = statement.with_for_update().execution_options(populate_existing=True)
    return list((await db.scalars(statement)).all())


def allocate(
    batches: list[InventoryBatch], request: DiscardPlanRequest
) -> list[tuple[InventoryBatch, int]]:
    if request.batch_id is not None:
        batches = [batch for batch in batches if batch.id == request.batch_id]
        if not batches:
            raise HTTPException(400, "指定批次不属于该商品、已过期或没有可处理库存")
    if sum(batch.remaining_quantity for batch in batches) < request.quantity:
        raise HTTPException(400, "废弃数量超过可处理库存，请重新查询")
    remaining = request.quantity
    result = []
    for batch in batches:
        quantity = min(batch.remaining_quantity, remaining)
        if quantity:
            result.append((batch, quantity))
            remaining -= quantity
        if not remaining:
            break
    return result


def plan_items(allocation: list[tuple[InventoryBatch, int]]) -> list[DiscardItemResponse]:
    return [
        DiscardItemResponse(
            batch_id=batch.id,
            batch_no=batch.batch_no,
            expiration_date=batch.expiration_date,
            quantity=quantity,
            unit_cost=batch.purchase_item.unit_cost,
            total_cost=(batch.purchase_item.unit_cost * quantity).quantize(Decimal("0.01")),
            before_quantity=batch.remaining_quantity,
            after_quantity=batch.remaining_quantity - quantity,
        )
        for batch, quantity in allocation
    ]


async def get_discard_stock(
    product_id: int, employee_id: int, db: AsyncSession
) -> DiscardStockResponse:
    employee = await validate_actor(employee_id, db, write=True)
    product = await load_product(product_id, employee, db)
    batches = await eligible_batches(product, db)
    return DiscardStockResponse(
        product_id=product.id,
        product_no=product.product_no,
        product_name=product.name,
        department_id=product.department_id,
        department_name=product.department.name,
        available_quantity=sum(batch.remaining_quantity for batch in batches),
        batches=[
            DiscardBatchResponse(
                batch_id=batch.id,
                batch_no=batch.batch_no,
                expiration_date=batch.expiration_date,
                remaining_quantity=batch.remaining_quantity,
                unit_cost=batch.purchase_item.unit_cost,
            )
            for batch in batches
        ],
    )


async def preview_discard(
    request: DiscardPlanRequest, employee_id: int, db: AsyncSession
) -> DiscardPlanResponse:
    employee = await validate_actor(employee_id, db, write=True)
    product = await load_product(request.product_id, employee, db)
    items = plan_items(allocate(await eligible_batches(product, db), request))
    return DiscardPlanResponse(
        product_id=product.id,
        product_name=product.name,
        quantity=request.quantity,
        total_cost=sum((item.total_cost for item in items), Decimal("0.00")),
        items=items,
    )


async def record_discard(
    *,
    product: Product,
    allocation: list[tuple[InventoryBatch, int]],
    request_key: str,
    reason_code: str,
    note: str | None,
    employee: Employee | None,
    requested_batch_id: int | None,
    db: AsyncSession,
) -> InventoryDiscard:
    """调用方先锁定商品与批次；库存、损耗单和流水在同一事务中写入。"""
    items = plan_items(allocation)
    record = InventoryDiscard(
        store_id=product.store_id,
        request_key=request_key,
        product_id=product.id,
        product_no=product.product_no,
        product_name=product.name,
        department_id=product.department_id,
        department_name=product.department.name,
        employee_id=employee.id if employee else None,
        employee_name=employee.name if employee else None,
        reason_code=reason_code,
        note=note,
        requested_batch_id=requested_batch_id,
        quantity=sum(item.quantity for item in items),
        total_cost=sum((item.total_cost for item in items), Decimal("0.00")),
        created_at=business_now(),
        items=[
            InventoryDiscardItem(store_id=product.store_id, **item.model_dump()) for item in items
        ],
    )
    db.add(record)
    await db.flush()
    for batch, quantity in allocation:
        before = batch.remaining_quantity
        batch.remaining_quantity -= quantity
        if not batch.remaining_quantity:
            batch.status = InventoryBatchStatus.SOLD_OUT
        elif batch.expiration_date is not None and batch.expiration_date < business_now().date():
            batch.status = InventoryBatchStatus.EXPIRED
        elif (
            batch.expiration_date is not None
            and product.expiry_warning_days is not None
            and batch.expiration_date
            <= business_now().date() + timedelta(days=product.expiry_warning_days)
        ):
            batch.status = InventoryBatchStatus.NEAR_EXPIRY
        else:
            batch.status = InventoryBatchStatus.AVAILABLE
        await create_operation_audit_log(
            employee_id=employee.id if employee else None,
            module="inventory",
            action="discard_expired" if reason_code == "expired" else "discard_manual",
            target_type="inventory_batch",
            target_id=batch.id,
            before_data={"remaining_quantity": before},
            after_data={
                "remaining_quantity": batch.remaining_quantity,
                "discarded_quantity": quantity,
                "discard_id": record.id,
                "reason_code": reason_code,
                "loss_cost": str(batch.purchase_item.unit_cost * quantity),
            },
            reason=note or reason_code,
            store_id=product.store_id,
            db=db,
        )
    await db.flush()
    # 使用锁定读取获得最新数量，避免 MySQL REPEATABLE READ 的旧快照覆盖库存。
    product.stock_quantity = sum(
        (
            await db.scalars(
                select(InventoryBatch.remaining_quantity)
                .where(
                    InventoryBatch.store_id == product.store_id,
                    InventoryBatch.product_id == product.id,
                )
                .with_for_update()
            )
        ).all()
    )
    await db.flush()
    return record


async def create_discard(
    request: DiscardCreateRequest, employee_id: int, db: AsyncSession
) -> DiscardResponse:
    employee = await validate_actor(employee_id, db, write=True)
    # 商品锁同时串行化同商品的销售、废弃和同一请求重试。
    product = await load_product(request.product_id, employee, db, lock=True)
    existing = await db.scalar(
        select(InventoryDiscard)
        .where(
            InventoryDiscard.store_id == product.store_id,
            InventoryDiscard.request_key == str(request.request_id),
        )
        .with_for_update()
        .options(lazyload(InventoryDiscard.items))
        .execution_options(populate_existing=True)
    )
    if existing is not None:
        if (
            existing.product_id != request.product_id
            or existing.quantity != request.quantity
            or existing.requested_batch_id != request.batch_id
            or existing.reason_code != request.reason_code
            or existing.note != request.note
            or existing.employee_id != employee.id
        ):
            raise HTTPException(409, "该请求编号已用于不同的废弃操作")
        # 父单和明细均使用当前锁定读取，重复请求不能返回旧快照中的空明细。
        items = list(
            (
                await db.scalars(
                    select(InventoryDiscardItem)
                    .where(
                        InventoryDiscardItem.discard_id == existing.id,
                    )
                    .with_for_update()
                    .execution_options(populate_existing=True)
                )
            ).all()
        )
        set_committed_value(existing, "items", items)
        response = DiscardResponse.model_validate(existing)
        await db.commit()
        return response
    allocation = allocate(await eligible_batches(product, db, lock=True), request)
    record = await record_discard(
        product=product,
        allocation=allocation,
        request_key=str(request.request_id),
        reason_code=request.reason_code,
        note=request.note,
        employee=employee,
        requested_batch_id=request.batch_id,
        db=db,
    )
    response = DiscardResponse.model_validate(record)
    await db.commit()
    return response


async def list_discards(
    request: DiscardListRequest, employee_id: int, db: AsyncSession
) -> DiscardListResponse:
    employee = await validate_actor(employee_id, db)
    if employee.role not in (
        EmployeeRole.STORE_MANAGER,
        EmployeeRole.REGULAR_EMPLOYEE,
        EmployeeRole.HEADQUARTERS,
    ):
        raise HTTPException(403, "只有店长、正式员工或总部可以查看废弃记录")
    if request.start_date and request.end_date and request.start_date > request.end_date:
        raise HTTPException(400, "开始日期不能晚于结束日期")
    conditions = []
    if request.product_id is not None:
        conditions.append(InventoryDiscard.product_id == request.product_id)
    if request.department_id is not None:
        conditions.append(InventoryDiscard.department_id == request.department_id)
    if request.reason_code:
        conditions.append(InventoryDiscard.reason_code == request.reason_code)
    if request.mode:
        conditions.append(
            InventoryDiscard.employee_id.is_(None)
            if request.mode == "automatic"
            else InventoryDiscard.employee_id.is_not(None)
        )
    if request.start_date:
        conditions.append(
            InventoryDiscard.created_at >= datetime.combine(request.start_date, time.min)
        )
    if request.end_date:
        conditions.append(
            InventoryDiscard.created_at
            < datetime.combine(request.end_date + timedelta(days=1), time.min)
        )
    # 显式门店条件也供直接 Service 调用使用，避免依赖关系加载隐藏历史记录。
    selected = db.info.get("read_store_id", employee.store_id)
    if selected is not None:
        conditions.append(InventoryDiscard.store_id == selected)
    if employee.role == EmployeeRole.REGULAR_EMPLOYEE:
        conditions.append(InventoryDiscard.department_id == employee.department_id)
    count, quantity, cost = (
        await db.execute(
            select(
                func.count(InventoryDiscard.id),
                func.coalesce(func.sum(InventoryDiscard.quantity), 0),
                func.coalesce(func.sum(InventoryDiscard.total_cost), 0),
            ).where(*conditions)
        )
    ).one()
    records = (
        await db.scalars(
            select(InventoryDiscard)
            .where(*conditions)
            .order_by(
                InventoryDiscard.created_at.desc(),
                InventoryDiscard.id.desc(),
            )
            .offset((request.page - 1) * request.page_size)
            .limit(request.page_size)
        )
    ).all()
    return DiscardListResponse(
        items=[DiscardResponse.model_validate(record) for record in records],
        page=request.page,
        page_size=request.page_size,
        total=count,
        total_pages=(count + request.page_size - 1) // request.page_size,
        total_quantity=quantity,
        total_cost=cost,
    )


async def discard_expired_product(product_id: int, current_date: date, db: AsyncSession) -> int:
    """后台按商品短事务处理，日期当天有效；重复运行只处理正数剩余库存。"""
    product = await db.scalar(
        select(Product)
        .where(Product.id == product_id)
        .options(
            selectinload(Product.department),
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if product is None:
        return 0
    batches = list(
        (
            await db.scalars(
                select(InventoryBatch)
                .where(
                    InventoryBatch.product_id == product.id,
                    InventoryBatch.store_id == product.store_id,
                    InventoryBatch.expiration_date < current_date,
                    InventoryBatch.remaining_quantity > 0,
                )
                .options(selectinload(InventoryBatch.purchase_item))
                .order_by(InventoryBatch.id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
        ).all()
    )
    for batch in batches:
        await record_discard(
            product=product,
            allocation=[(batch, batch.remaining_quantity)],
            # 盘点恢复过期库存后，仍应再次废弃；每次记录独立且只扣最新正数库存。
            request_key=f"expired:{batch.id}:{batch.remaining_quantity}:{business_now().isoformat()}",
            reason_code="expired",
            note=None,
            employee=None,
            requested_batch_id=batch.id,
            db=db,
        )
    return len(batches)
