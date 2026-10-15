"""库存批次业务逻辑。"""

from datetime import date, timedelta

from fastapi import HTTPException, Request
from fastapi import status as http_status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.business_time import business_now
from app.crud import inventory_batches as data_access
from app.crud.auth import get_employee_by_id
from app.crud.inventory_batches import get_inventory_batch_by_id, get_inventory_batches_list
from app.crud.operation_audit_logs import create_operation_audit_log
from app.crud.stores import department_is_enabled, first_active_store_id, get_store_by_id
from app.models.enums import EmployeeRole, InventoryBatchStatus
from app.models.inventory_batch import InventoryBatch
from app.schemas.inventory_batches_requests import (
    InventoryBatchDiscardRequest,
    InventoryBatchQuantityUpdateRequest,
)
from app.schemas.inventory_batches_responses import (
    InventoryBatchDetailResponse,
    InventoryBatchItemResponse,
    InventoryBatchListResponse,
)


# region 获取库存批次列表
async def get_inventory_batches_list_service(
    # page：前端指定的当前页码。
    page: int,
    # page_size：前端指定的每页数量。
    page_size: int,
    # status：可选批次状态筛选条件。
    status: InventoryBatchStatus | None,
    # 以下参数分别按照供应商、商品、部门和到期日期范围筛选。
    supplier_id: int | None,
    product_id: int | None,
    department_id: int | None,
    expiration_start: date | None,
    expiration_end: date | None,
    # current_employee_id：当前登录员工 ID，用于检查账号有效性。
    current_employee_id: int,
    # db：当前请求使用的异步数据库会话。
    db: AsyncSession,
    *,
    http_request: Request | None = None,
) -> InventoryBatchListResponse:
    """验证当前账号有效，并组装全部部门的分页库存批次列表。"""

    # 本接口在服务层明确检查店铺范围；不依赖数据库自动事件。
    if http_request is not None:
        access_employee = await get_employee_by_id(employee_id=current_employee_id, db=db)
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

    # 第一步：查询当前登录员工并检查账号的最新状态。
    current_employee = await get_employee_by_id(
        employee_id=current_employee_id,
        db=db,
    )
    if current_employee is None:
        raise HTTPException(
            status_code=http_status.HTTP_401_UNAUTHORIZED,
            detail="当前登录员工不存在",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 员工账号已被停用时，即使旧令牌尚未过期也不能继续查询。
    if not current_employee.is_active:
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail="当前账号已停用",
        )

    # 使用初始密码的员工需要先完成首次密码修改。
    if current_employee.must_change_password:
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail="请先修改初始密码",
        )

    # 开始日期晚于结束日期时无法形成有效范围，直接返回清晰的参数错误。
    if (
        expiration_start is not None
        and expiration_end is not None
        and expiration_start > expiration_end
    ):
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail="最早到期日期不能晚于最晚到期日期",
        )

    # 第二步：获取当前页批次以及符合筛选条件的总记录数。
    # 所有有效员工都查询全部部门，不按照角色或所属部门过滤。
    batches, total = await get_inventory_batches_list(
        page=page,
        page_size=page_size,
        status=status,
        supplier_id=supplier_id,
        product_id=product_id,
        department_id=department_id,
        expiration_start=expiration_start,
        expiration_end=expiration_end,
        db=db,
    )

    # 第三步：把批次、商品和部门数据组装成前端需要的平铺列表项。
    items: list[InventoryBatchItemResponse] = []
    for batch in batches:
        item = InventoryBatchItemResponse(
            id=batch.id,
            batch_no=batch.batch_no,
            product_no=batch.product.product_no,
            product_name=batch.product.name,
            department_name=batch.product.department.name,
            initial_quantity=batch.initial_quantity,
            remaining_quantity=batch.remaining_quantity,
            production_date=batch.production_date,
            expiration_date=batch.expiration_date,
            status=batch.status,
            arrived_at=batch.arrived_at,
        )
        items.append(item)

    # 第四步：向上取整计算总页数；没有记录时结果为 0。
    total_pages = (total + page_size - 1) // page_size

    return InventoryBatchListResponse(
        items=items,
        page=page,
        page_size=page_size,
        total=total,
        total_pages=total_pages,
    )


# endregion


# region 修改库存批次数量
async def update_inventory_batch_quantity_service(
    batch_id: int,
    request: InventoryBatchQuantityUpdateRequest,
    current_employee_id: int,
    db: AsyncSession,
    *,
    http_request: Request | None = None,
) -> InventoryBatchDetailResponse:
    """校验账号及部门权限，修改批次库存并同步商品总库存。"""

    # 本接口在服务层明确检查店铺范围；不依赖数据库自动事件。
    if http_request is not None:
        access_employee = await get_employee_by_id(employee_id=current_employee_id, db=db)
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

    # 第一步：执行与其他受保护接口相同的基础账号验证。
    current_employee = await get_employee_by_id(
        employee_id=current_employee_id,
        db=db,
    )
    if current_employee is None:
        raise HTTPException(
            status_code=http_status.HTTP_401_UNAUTHORIZED,
            detail="当前登录员工不存在",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not current_employee.is_active:
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail="当前账号已停用",
        )
    if current_employee.must_change_password:
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail="请先修改初始密码",
        )

    # 第二步：只有店长和正式员工能够人工调整库存。
    if current_employee.role not in (
        EmployeeRole.STORE_MANAGER,
        EmployeeRole.REGULAR_EMPLOYEE,
    ):
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail="只有店长或正式员工可以修改库存批次数量",
        )

    # 第三步：锁定该批次及其商品行，再读取最新库存。
    # 在本事务提交前，销售扣库存和其他盘点请求会等待，避免互相覆盖。
    batch = await get_inventory_batch_by_id(
        batch_id=batch_id,
        db=db,
        for_update=True,
    )
    if batch is None:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail="库存批次不存在",
        )

    # 明确检查所属店和部门，不再依赖保存前的自动事件。
    if db.info.get("store_context"):
        if batch.store_id != db.info.get("own_store_id"):
            raise HTTPException(403, "只能修改所属门店数据")
        if not await department_is_enabled(batch.store_id, batch.product.department_id, db):
            raise HTTPException(400, "本店未启用此部门")

    # 店长可以修改所有部门；正式员工只能修改自己所属部门的批次。
    if (
        current_employee.role == EmployeeRole.REGULAR_EMPLOYEE
        and current_employee.department_id != batch.product.department_id
    ):
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail="正式员工只能修改自己所属部门的库存批次",
        )

    # 剩余数量不能超过该批次到货时记录的初始数量。
    if request.remaining_quantity > batch.initial_quantity:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail="批次剩余数量不能超过到货初始数量",
        )

    await update_inventory_batch_quantity(
        batch=batch,
        remaining_quantity=request.remaining_quantity,
        employee_id=current_employee.id,
        reason=request.reason,
        db=db,
    )
    await db.commit()

    # 提交后重新读取最新值，再复用详情 Service 组装统一响应。
    return await get_inventory_batch_detail_service(
        batch_id=batch_id,
        current_employee_id=current_employee_id,
        db=db,
    )


# endregion


# region 废弃过期批次库存
async def discard_expired_inventory_batch_service(
    batch_id: int,
    request: InventoryBatchDiscardRequest,
    current_employee_id: int,
    db: AsyncSession,
    *,
    http_request: Request | None = None,
) -> InventoryBatchDetailResponse:
    """验证账号、部门和过期状态，废弃批次剩余库存并同步商品库存。"""

    # 本接口在服务层明确检查店铺范围；不依赖数据库自动事件。
    if http_request is not None:
        access_employee = await get_employee_by_id(employee_id=current_employee_id, db=db)
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

    # 第一步：确认当前员工存在、账号启用并且已经修改初始密码。
    current_employee = await get_employee_by_id(
        employee_id=current_employee_id,
        db=db,
    )
    if current_employee is None:
        raise HTTPException(
            status_code=http_status.HTTP_401_UNAUTHORIZED,
            detail="当前登录员工不存在",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not current_employee.is_active:
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail="当前账号已停用",
        )
    if current_employee.must_change_password:
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail="请先修改初始密码",
        )

    # 第二步：店长可以处理全部部门，正式员工只能处理自己部门的过期批次。
    if current_employee.role not in (
        EmployeeRole.STORE_MANAGER,
        EmployeeRole.REGULAR_EMPLOYEE,
    ):
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail="只有店长或正式员工可以废弃过期库存",
        )

    # 废弃也会修改批次和商品库存，因此使用与销售相同的行锁。
    batch = await get_inventory_batch_by_id(
        batch_id=batch_id,
        db=db,
        for_update=True,
    )
    if batch is None:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail="库存批次不存在",
        )

    # 明确检查所属店和部门，不再依赖保存前的自动事件。
    if db.info.get("store_context"):
        if batch.store_id != db.info.get("own_store_id"):
            raise HTTPException(403, "只能修改所属门店数据")
        if not await department_is_enabled(batch.store_id, batch.product.department_id, db):
            raise HTTPException(400, "本店未启用此部门")

    if (
        current_employee.role == EmployeeRole.REGULAR_EMPLOYEE
        and current_employee.department_id != batch.product.department_id
    ):
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail="正式员工只能废弃自己所属部门的过期库存",
        )

    # 第三步：以到期日期判断是否真正过期，不依赖凌晨状态任务是否已经执行。
    if batch.expiration_date is None or batch.expiration_date >= business_now().date():
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail="只有已经过期的库存批次可以废弃",
        )
    if batch.remaining_quantity == 0:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail="该过期批次已经没有剩余库存",
        )

    await discard_expired_inventory_batch(
        batch=batch,
        employee_id=current_employee.id,
        reason=request.reason,
        db=db,
    )
    await db.commit()

    # 第四步：重新查询并返回废弃后的批次详情。
    return await get_inventory_batch_detail_service(
        batch_id=batch_id,
        current_employee_id=current_employee_id,
        db=db,
    )


# endregion


# region 获取库存批次详情
async def get_inventory_batch_detail_service(
    # batch_id：准备查看的库存批次 ID。
    batch_id: int,
    # current_employee_id：当前登录员工 ID，用于检查账号有效性。
    current_employee_id: int,
    # db：当前请求使用的异步数据库会话。
    db: AsyncSession,
    *,
    http_request: Request | None = None,
) -> InventoryBatchDetailResponse:
    """验证当前账号有效，并返回指定库存批次的完整详情。"""

    # 本接口在服务层明确检查店铺范围；不依赖数据库自动事件。
    if http_request is not None:
        access_employee = await get_employee_by_id(employee_id=current_employee_id, db=db)
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

    # 第一步：检查当前员工存在、账号启用并且已经修改初始密码。
    # 所有员工角色均可查看，不进行角色和所属部门限制。
    current_employee = await get_employee_by_id(
        employee_id=current_employee_id,
        db=db,
    )
    if current_employee is None:
        raise HTTPException(
            status_code=http_status.HTTP_401_UNAUTHORIZED,
            detail="当前登录员工不存在",
            headers={"WWW-Authenticate": "Bearer"},
        )
    # 停用账号不能继续访问库存批次数据。
    if not current_employee.is_active:
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail="当前账号已停用",
        )
    # 使用初始密码的员工需要先完成首次密码修改。
    if current_employee.must_change_password:
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail="请先修改初始密码",
        )

    # 第二步：查询批次以及商品、部门、分类、进货明细和进货单关系。
    batch = await get_inventory_batch_by_id(batch_id=batch_id, db=db)
    if batch is None:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail="库存批次不存在",
        )

    # 第三步：把多个关联表中的字段组装成平铺的详情响应。
    return InventoryBatchDetailResponse(
        id=batch.id,
        batch_no=batch.batch_no,
        product_id=batch.product_id,
        product_no=batch.product.product_no,
        product_name=batch.product.name,
        department_id=batch.product.department_id,
        department_name=batch.product.department.name,
        category_id=batch.product.category_id,
        category_name=batch.product.category.name,
        supplier_name=batch.purchase_item.supplier_name_snapshot,
        purchase_no=batch.purchase_item.purchase.purchase_no,
        purchase_item_id=batch.purchase_item_id,
        unit_cost=batch.purchase_item.unit_cost,
        initial_quantity=batch.initial_quantity,
        remaining_quantity=batch.remaining_quantity,
        production_date=batch.production_date,
        expiration_date=batch.expiration_date,
        status=batch.status,
        arrived_at=batch.arrived_at,
        created_at=batch.created_at,
        updated_at=batch.updated_at,
    )


# endregion


__all__ = [
    "discard_expired_inventory_batch_service",
    "get_inventory_batch_detail_service",
    "get_inventory_batches_list_service",
    "update_inventory_batch_quantity_service",
]


async def refresh_inventory_batch_statuses(current_date: date, db: AsyncSession) -> int:
    """根据剩余数量和临期日期刷新全部批次状态，并返回变更数量。"""
    result = await data_access.get_batches_for_status_refresh(db=db)
    batches = list(result.all())
    changed_count = 0
    for batch in batches:
        if batch.remaining_quantity == 0:
            new_status = InventoryBatchStatus.SOLD_OUT
        elif batch.expiration_date is not None and batch.expiration_date < current_date:
            new_status = InventoryBatchStatus.EXPIRED
        elif (
            batch.expiration_date is not None
            and batch.product.expiry_warning_days is not None
            and (
                batch.expiration_date
                <= current_date + timedelta(days=batch.product.expiry_warning_days)
            )
        ):
            new_status = InventoryBatchStatus.NEAR_EXPIRY
        else:
            new_status = InventoryBatchStatus.AVAILABLE
        if batch.status != new_status:
            previous_status = batch.status
            batch.status = new_status
            changed_count += 1
            await create_operation_audit_log(
                employee_id=None,
                module="inventory",
                action="refresh_batch_status",
                target_type="inventory_batch",
                target_id=batch.id,
                before_data={"status": previous_status},
                after_data={"status": new_status},
                reason="系统根据库存数量和到期日期自动刷新批次状态",
                store_id=batch.store_id,
                db=db,
            )
    await db.flush()
    return changed_count


async def update_inventory_batch_quantity(
    batch: InventoryBatch,
    remaining_quantity: int,
    employee_id: int,
    reason: str | None,
    db: AsyncSession,
) -> InventoryBatch:
    """修改批次剩余数量，记录调整历史并重新汇总商品总库存。"""
    before_quantity = batch.remaining_quantity
    batch.remaining_quantity = remaining_quantity
    if remaining_quantity == 0:
        batch.status = InventoryBatchStatus.SOLD_OUT
    elif batch.expiration_date is not None and batch.expiration_date < business_now().date():
        batch.status = InventoryBatchStatus.EXPIRED
    elif (
        batch.expiration_date is not None
        and batch.product.expiry_warning_days is not None
        and (
            batch.expiration_date
            <= business_now().date() + timedelta(days=batch.product.expiry_warning_days)
        )
    ):
        batch.status = InventoryBatchStatus.NEAR_EXPIRY
    else:
        batch.status = InventoryBatchStatus.AVAILABLE
    await db.flush()
    batch.product.stock_quantity = int(
        await data_access.get_product_for_stock_update(db=db, batch=batch) or 0
    )
    await create_operation_audit_log(
        employee_id=employee_id,
        module="inventory",
        action="update_quantity",
        target_type="inventory_batch",
        target_id=batch.id,
        before_data={"remaining_quantity": before_quantity},
        after_data={"remaining_quantity": remaining_quantity},
        reason=reason,
        db=db,
    )
    return batch


async def discard_expired_inventory_batch(
    batch: InventoryBatch, employee_id: int, reason: str | None, db: AsyncSession
) -> InventoryBatch:
    """清空一个过期批次的剩余库存，同步商品总库存并写入审计记录。"""
    from uuid import uuid4

    from app.crud.auth import get_employee_by_id
    from app.services.inventory_discards import record_discard

    employee = await get_employee_by_id(employee_id=employee_id, db=db)
    await record_discard(
        product=batch.product,
        allocation=[(batch, batch.remaining_quantity)],
        request_key=str(uuid4()),
        reason_code="expired",
        note=reason,
        employee=employee,
        requested_batch_id=batch.id,
        db=db,
    )
    return batch
