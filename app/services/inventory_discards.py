"""废弃计划、原子库存扣减、不可变损耗记录及自动过期处理。"""

from datetime import date, timedelta
from decimal import Decimal

from fastapi import HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import set_committed_value

from app.core.business_time import business_now
from app.crud import inventory_discards as data_access
from app.crud.auth import get_employee_by_id
from app.crud.operation_audit_logs import create_operation_audit_log
from app.crud.scheduler import get_expired_product_ids
from app.crud.stores import first_active_store_id, get_store_by_id
from app.models.employee import Employee
from app.models.enums import EmployeeRole, InventoryBatchStatus
from app.models.inventory_batch import InventoryBatch
from app.models.inventory_discard import InventoryDiscard, InventoryDiscardItem
from app.models.product import Product
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
    """验证账号可用性；write=True时限制手动废弃角色及所属门店。

    只校验账号级权限，具体商品及部门权限由load_product继续检查。
    停用、未改初始密码或跨店写入均拒绝，读操作也不能使用不存在账号。"""
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
    """读取本店商品并校验部门权限，lock=True用于真实废弃的串行化。

    正式员工仅所属部门；必须是本店启用部门。锁定读取重新载入当前数据，
    避免ORM旧对象或MySQL快照影响库存扣减。调用方负责事务提交或回滚。"""
    product = await data_access.get_discard_product(db=db, lock=lock, product_id=product_id)
    if product is None:
        raise HTTPException(404, "商品不存在")
    if product.store_id != employee.store_id:
        raise HTTPException(403, "只能废弃所属门店的商品")
    if (
        employee.role == EmployeeRole.REGULAR_EMPLOYEE
        and employee.department_id != product.department_id
    ):
        raise HTTPException(403, "正式员工只能废弃自己所属部门的商品")
    enabled = await data_access.get_product_department_enabled(db=db, product=product)
    if not enabled or product.department is None:
        raise HTTPException(400, "本店未启用此部门")
    return product


async def eligible_batches(
    product: Product, db: AsyncSession, *, lock: bool = False
) -> list[InventoryBatch]:
    """按最早到期优先返回已到货、有剩余且未过期的可手动处理批次。

    无到期日的批次排在后面，同到期日按到货时间及ID排序，保证稳定分配。
    过期库存由自动流程处理。真正提交时lock=True，预览不持有写锁。"""
    now = business_now()
    return list(
        (await data_access.get_discard_batches(db=db, lock=lock, now=now, product=product)).all()
    )


def allocate(
    batches: list[InventoryBatch], request: DiscardPlanRequest
) -> list[tuple[InventoryBatch, int]]:
    """在已排序批次中分配废弃数量，返回批次及本次扣减数量，不修改库存。

    指定batch_id时只用该批次；否则顺序分配。总可用量不足即拒绝，不部分扣减。
    返回结果用于预览或锁定后提交，预览结果不能作为库存仍充足的凭据。"""
    if request.batch_id is not None:
        batches_values = []
        for batches_batch in batches:
            if batches_batch.id == request.batch_id:
                batches_values.append(batches_batch)
        batches = batches_values
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
    """把分配结果转为成本和前后数量快照；金额使用批次进货成本而非现售价。"""
    result_values = []
    for result_batch, result_quantity in allocation:
        result_values.append(
            DiscardItemResponse(
                batch_id=result_batch.id,
                batch_no=result_batch.batch_no,
                expiration_date=result_batch.expiration_date,
                quantity=result_quantity,
                unit_cost=result_batch.purchase_item.unit_cost,
                total_cost=(result_batch.purchase_item.unit_cost * result_quantity).quantize(
                    Decimal("0.01")
                ),
                before_quantity=result_batch.remaining_quantity,
                after_quantity=result_batch.remaining_quantity - result_quantity,
            )
        )
    return result_values


async def get_discard_stock(
    product_id: int, employee_id: int, db: AsyncSession, *, http_request: Request | None = None
) -> DiscardStockResponse:
    """返回员工可处理商品的批次、可用量和进货成本，不写入库存。"""

    # 本接口在服务层明确检查店铺范围；不依赖数据库自动事件。
    if http_request is not None:
        access_employee = await get_employee_by_id(employee_id=employee_id, db=db)
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

    employee = await validate_actor(employee_id, db, write=True)
    product = await load_product(product_id, employee, db)
    batches = await eligible_batches(product, db)
    batches_value_values = []
    for batches_value_batch in batches:
        batches_value_values.append(
            DiscardBatchResponse(
                batch_id=batches_value_batch.id,
                batch_no=batches_value_batch.batch_no,
                expiration_date=batches_value_batch.expiration_date,
                remaining_quantity=batches_value_batch.remaining_quantity,
                unit_cost=batches_value_batch.purchase_item.unit_cost,
            )
        )
    batches_value = batches_value_values
    return DiscardStockResponse(
        product_id=product.id,
        product_no=product.product_no,
        product_name=product.name,
        department_id=product.department_id,
        department_name=product.department.name,
        available_quantity=sum(batch.remaining_quantity for batch in batches),
        batches=batches_value,
    )


async def preview_discard(
    request: DiscardPlanRequest,
    employee_id: int,
    db: AsyncSession,
    *,
    http_request: Request | None = None,
) -> DiscardPlanResponse:
    """预览废弃批次及实际成本；不加写锁、不保存，提交时必须重新校验。"""

    # 本接口在服务层明确检查店铺范围；不依赖数据库自动事件。
    if http_request is not None:
        access_employee = await get_employee_by_id(employee_id=employee_id, db=db)
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
    if employee:
        employee_id_value = employee.id
    else:
        employee_id_value = None
    if employee:
        employee_name_value = employee.name
    else:
        employee_name_value = None
    items_value_values = []
    for items_value_item in items:
        items_value_values.append(
            InventoryDiscardItem(store_id=product.store_id, **items_value_item.model_dump())
        )
    items_value = items_value_values
    record = InventoryDiscard(
        store_id=product.store_id,
        request_key=request_key,
        product_id=product.id,
        product_no=product.product_no,
        product_name=product.name,
        department_id=product.department_id,
        department_name=product.department.name,
        employee_id=employee_id_value,
        employee_name=employee_name_value,
        reason_code=reason_code,
        note=note,
        requested_batch_id=requested_batch_id,
        quantity=sum(item.quantity for item in items),
        total_cost=sum((item.total_cost for item in items), Decimal("0.00")),
        created_at=business_now(),
        items=items_value,
    )
    data_access.add_discard_record(db=db, record=record)
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
            and (
                batch.expiration_date
                <= business_now().date() + timedelta(days=product.expiry_warning_days)
            )
        ):
            batch.status = InventoryBatchStatus.NEAR_EXPIRY
        else:
            batch.status = InventoryBatchStatus.AVAILABLE
        if employee:
            employee_id_value_item = employee.id
        else:
            employee_id_value_item = None
        if reason_code == "expired":
            action_value = "discard_expired"
        else:
            action_value = "discard_manual"
        await create_operation_audit_log(
            employee_id=employee_id_value_item,
            module="inventory",
            action=action_value,
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
    product.stock_quantity = sum(
        (await data_access.get_remaining_batch_quantities(db=db, product=product)).all()
    )
    await db.flush()
    return record


async def create_discard(
    request: DiscardCreateRequest,
    employee_id: int,
    db: AsyncSession,
    *,
    http_request: Request | None = None,
) -> DiscardResponse:
    """按请求ID幂等地执行手动废弃，并将库存、损耗记录与审计一起提交。

    先锁商品，再检查已有请求和批次；同一请求不能改用不同数量、原因或员工。
    重复请求返回原记录而不再次扣减，发生异常由上层会话依赖回滚。"""

    # 本接口在服务层明确检查店铺范围；不依赖数据库自动事件。
    if http_request is not None:
        access_employee = await get_employee_by_id(employee_id=employee_id, db=db)
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
        if is_headquarters:
            raise HTTPException(403, "总部不执行门店日常业务")
        if selected_store_id != access_employee.store_id:
            raise HTTPException(403, "跨店查看为只读，不能修改其他门店")
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

    employee = await validate_actor(employee_id, db, write=True)
    # 商品锁同时串行化同商品的销售、废弃和同一请求重试。
    product = await load_product(request.product_id, employee, db, lock=True)
    existing = await data_access.get_discard_by_request_id(db=db, product=product, request=request)
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
            (await data_access.get_discard_items_for_update(db=db, existing=existing)).all()
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
    request: DiscardListRequest,
    employee_id: int,
    db: AsyncSession,
    *,
    http_request: Request | None = None,
) -> DiscardListResponse:
    """按授权门店、查询日期和筛选条件分页读取废弃记录及汇总。"""
    if http_request is not None:
        access_employee = await get_employee_by_id(employee_id=employee_id, db=db)
        if access_employee is None or not access_employee.is_active:
            raise HTTPException(401, "账号不存在或已停用")
        is_headquarters = access_employee.role == EmployeeRole.HEADQUARTERS
        selected_store_id = access_employee.store_id
        raw_store_id = http_request.headers.get("X-Store-ID")
        if not raw_store_id:
            raw_store_id = http_request.query_params.get("store_id")
        if raw_store_id == "all":
            if not is_headquarters:
                raise HTTPException(403, "只有总部经营报表支持全公司汇总")
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
    employee = await validate_actor(employee_id, db)
    if employee.role not in (
        EmployeeRole.STORE_MANAGER,
        EmployeeRole.REGULAR_EMPLOYEE,
        EmployeeRole.HEADQUARTERS,
    ):
        raise HTTPException(403, "只有店长、正式员工或总部可以查看废弃记录")
    if request.start_date and request.end_date and (request.start_date > request.end_date):
        raise HTTPException(400, "开始日期不能晚于结束日期")
    selected = db.info.get("read_store_id", employee.store_id)
    count, quantity, cost = (
        await data_access.get_discard_totals(
            db=db, employee=employee, request=request, selected=selected
        )
    ).one()
    records = (
        await data_access.get_discard_page(
            db=db, employee=employee, request=request, selected=selected
        )
    ).all()
    items_value_item_item_values = []
    for items_value_item_item_record in records:
        items_value_item_item_values.append(
            DiscardResponse.model_validate(items_value_item_item_record)
        )
    items_value_item_item = items_value_item_item_values
    return DiscardListResponse(
        items=items_value_item_item,
        page=request.page,
        page_size=request.page_size,
        total=count,
        total_pages=(count + request.page_size - 1) // request.page_size,
        total_quantity=quantity,
        total_cost=cost,
    )


async def discard_expired_product(product_id: int, current_date: date, db: AsyncSession) -> int:
    """后台按商品短事务处理，日期当天有效；重复运行只处理正数剩余库存。"""
    product = await data_access.get_expired_product_for_update(db=db, product_id=product_id)
    if product is None:
        return 0
    batches = list(
        (
            await data_access.get_expired_product_batches(
                db=db, current_date=current_date, product=product
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


async def get_expired_product_ids_service(today, db):
    """给过期废弃任务提供待处理商品；每个商品仍由废弃服务独立处理。"""
    return await get_expired_product_ids(today, db)
