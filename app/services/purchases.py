"""进货管理的业务逻辑。"""

from datetime import date, datetime, time, timedelta
from decimal import Decimal
from uuid import uuid4

from fastapi import HTTPException, Request
from fastapi import status as http_status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.business_time import business_now
from app.crud import purchases as data_access
from app.crud.auth import get_employee_by_id
from app.crud.business_sequence import next_business_sequence
from app.crud.employees import get_department_by_id
from app.crud.operation_audit_logs import create_operation_audit_log
from app.crud.purchases import (
    get_all_purchases,
    get_purchase_by_client_request_id,
    get_purchase_by_id,
)
from app.crud.stores import department_is_enabled, first_active_store_id, get_store_by_id
from app.models.enums import EmployeeRole, InventoryBatchStatus, ProductStatus, PurchaseStatus
from app.models.inventory_batch import InventoryBatch
from app.models.product import Product
from app.models.purchase import Purchase
from app.models.purchase_item import PurchaseItem
from app.schemas.base import ResponseModel
from app.schemas.purchases_requests import CreatePurchaseRequest
from app.schemas.purchases_responses import (
    PurchaseDetailResponse,
    PurchaseItemResponse,
    PurchaseListItemResponse,
    PurchaseListResponse,
)


# region 获取进货单列表
async def get_purchases_list_service(
    page: int,
    page_size: int,
    purchase_no: str | None,
    department_id: int | None,
    ordered_at: date | None,
    arrived_at: date | None,
    purchase_status: PurchaseStatus | None,
    current_employee_id: int,
    db: AsyncSession,
    *,
    http_request: Request | None = None,
) -> PurchaseListResponse:
    """验证当前员工状态，并返回筛选和分页后的进货单列表。"""

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

    current_employee = await get_employee_by_id(employee_id=current_employee_id, db=db)
    if current_employee is None:
        raise HTTPException(
            status_code=http_status.HTTP_401_UNAUTHORIZED,
            detail="当前登录员工不存在",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not current_employee.is_active:
        raise HTTPException(status_code=http_status.HTTP_403_FORBIDDEN, detail="账号已停用")
    if current_employee.must_change_password:
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail="请先修改初始密码",
        )

    offset = (page - 1) * page_size
    # 调用 CRUD 执行进货单分页查询。
    purchases, total = await get_all_purchases(
        offset=offset,
        page_size=page_size,
        purchase_no=purchase_no,
        department_id=department_id,
        ordered_at=ordered_at,
        arrived_at=arrived_at,
        purchase_status=purchase_status,
        db=db,
    )

    items: list[PurchaseListItemResponse] = []
    for purchase, item_count, total_quantity in purchases:
        # 待到货进货单没有签收员工，因此签收员工姓名默认返回None。
        received_by_name = None
        if purchase.received_by_employee is not None:
            received_by_name = purchase.received_by_employee.name

        items.append(
            PurchaseListItemResponse(
                id=purchase.id,
                purchase_no=purchase.purchase_no,
                department_id=purchase.department_id,
                department_name=purchase.department.name,
                created_by=purchase.created_by,
                created_by_name=purchase.created_by_employee.name,
                received_by=purchase.received_by,
                received_by_name=received_by_name,
                ordered_at=purchase.ordered_at,
                expected_arrival_at=purchase.expected_arrival_at,
                arrived_at=purchase.arrived_at,
                total_amount=purchase.total_amount,
                status=purchase.status,
                item_count=item_count,
                total_quantity=total_quantity,
                created_at=purchase.created_at,
                updated_at=purchase.updated_at,
            )
        )

    return PurchaseListResponse(
        items=items,
        page=page,
        page_size=page_size,
        total=total,
        total_pages=(total + page_size - 1) // page_size,
    )


# endregion


# region 获取进货单详情
async def get_purchase_detail_service(
    purchase_id: int,
    current_employee_id: int,
    db: AsyncSession,
    *,
    http_request: Request | None = None,
) -> PurchaseDetailResponse:
    """验证当前员工状态，并返回进货单及其全部商品明细。"""

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

    current_employee = await get_employee_by_id(employee_id=current_employee_id, db=db)
    if current_employee is None:
        raise HTTPException(
            status_code=http_status.HTTP_401_UNAUTHORIZED,
            detail="当前登录员工不存在",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not current_employee.is_active:
        raise HTTPException(status_code=http_status.HTTP_403_FORBIDDEN, detail="账号已停用")
    if current_employee.must_change_password:
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail="请先修改初始密码",
        )

    # 根据进货单 ID 查询主表、部门、员工和全部明细。
    purchase = await get_purchase_by_id(purchase_id=purchase_id, db=db)
    if purchase is None:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="进货单不存在")

    received_by_name = None
    if purchase.received_by_employee is not None:
        received_by_name = purchase.received_by_employee.name

    # 明细里的名称使用下单快照，之后修改正式商品或供应商名称不会改变历史单据。
    detail_items: list[PurchaseItemResponse] = []
    total_quantity = 0
    for purchase_item in purchase.items:
        total_quantity += purchase_item.quantity
        detail_items.append(
            PurchaseItemResponse(
                id=purchase_item.id,
                supplier_product_id=purchase_item.supplier_product_id,
                product_id=purchase_item.product_id,
                supplier_id=purchase_item.supplier_id,
                product_no=purchase_item.product_no_snapshot,
                product_name=purchase_item.product_name_snapshot,
                supplier_name=purchase_item.supplier_name_snapshot,
                quantity=purchase_item.quantity,
                unit_cost=purchase_item.unit_cost,
                subtotal=purchase_item.subtotal,
                production_date=purchase_item.production_date,
                expiration_date=purchase_item.expiration_date,
            )
        )

    return PurchaseDetailResponse(
        id=purchase.id,
        purchase_no=purchase.purchase_no,
        department_id=purchase.department_id,
        department_name=purchase.department.name,
        created_by=purchase.created_by,
        created_by_name=purchase.created_by_employee.name,
        received_by=purchase.received_by,
        received_by_name=received_by_name,
        ordered_at=purchase.ordered_at,
        expected_arrival_at=purchase.expected_arrival_at,
        arrived_at=purchase.arrived_at,
        total_amount=purchase.total_amount,
        status=purchase.status,
        item_count=len(detail_items),
        total_quantity=total_quantity,
        created_at=purchase.created_at,
        updated_at=purchase.updated_at,
        items=detail_items,
    )


# endregion


# region 创建进货单
async def create_purchase_service(
    purchase: CreatePurchaseRequest,
    current_employee_id: int,
    db: AsyncSession,
    *,
    http_request: Request | None = None,
) -> PurchaseDetailResponse:
    """校验请求并创建进货单，最后返回完整的进货单详情。"""

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

    if purchase.client_request_id:
        request_id = str(purchase.client_request_id)
    else:
        request_id = None
    if request_id:
        existing_purchase = await get_purchase_by_client_request_id(request_id, db)
        if existing_purchase is not None:
            return await get_purchase_detail_service(
                purchase_id=existing_purchase.id,
                current_employee_id=current_employee_id,
                db=db,
            )

    # current_employee_id 是当前登录员工的 ID，先确认该账号仍可正常使用。
    current_employee = await get_employee_by_id(db=db, employee_id=current_employee_id)
    if current_employee is None:
        raise HTTPException(
            status_code=http_status.HTTP_401_UNAUTHORIZED,
            detail="当前登录员工不存在",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not current_employee.is_active:
        raise HTTPException(status_code=http_status.HTTP_403_FORBIDDEN, detail="账号已停用")
    if current_employee.must_change_password:
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail="请先修改初始密码",
        )

    now = business_now()
    arrival_date = purchase.expected_arrival_date or now.date() + timedelta(days=2)
    cutoff = datetime.combine(arrival_date - timedelta(days=2), time(hour=12))
    if now >= cutoff:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail="进货单须在到货日前两天的12:00前提交（日本时间）",
        )
    if purchase.expected_arrival_date is not None:
        earliest = now.date()
        latest = now.date() + timedelta(days=30)
        if not earliest <= purchase.expected_arrival_date <= latest:
            raise HTTPException(400, "预计到货日期须在今天至30天内")

    # 只有店长和正式员工可以创建进货单，契约工不能创建。
    if current_employee.role not in (
        EmployeeRole.STORE_MANAGER,
        EmployeeRole.REGULAR_EMPLOYEE,
    ):
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail="只有店长或正式员工可以创建进货单",
        )

    # department_id 是进货单所属部门的 ID，不能使用不存在或已停用的部门。
    department = await get_department_by_id(department_id=purchase.department_id, db=db)
    if department is None:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="部门不存在")
    if not department.is_active:
        raise HTTPException(status_code=http_status.HTTP_400_BAD_REQUEST, detail="部门已停用")
    if (
        current_employee.role == EmployeeRole.REGULAR_EMPLOYEE
        and current_employee.department_id != purchase.department_id
    ):
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail="正式员工只能为自己所属部门创建进货单",
        )

    # 同一张进货单不能重复添加同一个供应商商品目录项目。
    supplier_product_ids_values = []
    for supplier_product_ids_item in purchase.items:
        supplier_product_ids_values.append(supplier_product_ids_item.supplier_product_id)
    supplier_product_ids = supplier_product_ids_values
    if len(supplier_product_ids) != len(set(supplier_product_ids)):
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail="同一张进货单不能重复添加相同的供应商商品",
        )

    # 请求模型只检查单个字段，这里检查生产日期和到期日期之间的关系。
    for item in purchase.items:
        if (
            item.production_date is not None
            and item.expiration_date is not None
            and item.expiration_date < item.production_date
        ):
            raise HTTPException(
                status_code=http_status.HTTP_400_BAD_REQUEST,
                detail=f"供应商商品目录ID {item.supplier_product_id} 的到期日期不能早于生产日期",
            )

    try:
        # CRUD 同时新增 purchase 主表和 purchase_item 明细表，但不会提交事务。
        new_purchase = await create_purchase_records(
            purchase=purchase,
            created_by=current_employee_id,
            db=db,
        )

        # 主表和明细由同一个 CRUD 创建，这里用一条审计记录描述整张进货单的创建。
        items_value_values = []
        for items_value_item in new_purchase.items:
            items_value_values.append(
                {
                    "purchase_item_id": items_value_item.id,
                    "supplier_product_id": items_value_item.supplier_product_id,
                    "quantity": items_value_item.quantity,
                    "unit_cost": items_value_item.unit_cost,
                    "subtotal": items_value_item.subtotal,
                }
            )
        items_value = items_value_values
        await create_operation_audit_log(
            employee_id=current_employee_id,
            module="purchase",
            action="create",
            target_type="purchase",
            target_id=new_purchase.id,
            before_data=None,
            after_data={
                "purchase_no": new_purchase.purchase_no,
                "department_id": new_purchase.department_id,
                "status": new_purchase.status,
                "total_amount": new_purchase.total_amount,
                "item_count": len(new_purchase.items),
                "items": items_value,
            },
            reason=None,
            db=db,
        )

        # 复用详情服务，把 ORM 数据组装成接口要求的 PurchaseDetailResponse。
        # flush 已经生成了 new_purchase.id，未 commit 时也能在当前事务内查询。
        response = await get_purchase_detail_service(
            purchase_id=new_purchase.id,
            current_employee_id=current_employee_id,
            db=db,
        )
        await db.commit()
        return response
    except ValueError as error:
        # CRUD 在供应商商品目录 ID 不存在时会抛出 ValueError。
        await db.rollback()
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail=str(error),
        ) from error
    except IntegrityError as error:
        # 自动生成的进货单号发生唯一键冲突时，撤销本次事务。
        await db.rollback()
        if request_id:
            existing_purchase = await get_purchase_by_client_request_id(request_id, db)
            if existing_purchase is not None:
                return await get_purchase_detail_service(
                    purchase_id=existing_purchase.id,
                    current_employee_id=current_employee_id,
                    db=db,
                )
        raise HTTPException(
            status_code=http_status.HTTP_409_CONFLICT,
            detail="进货单号冲突，请重新提交",
        ) from error


# endregion


# region 自动签收进货单
async def auto_receive_purchases_service(
    current_employee_id: int, db: AsyncSession, *, http_request: Request | None = None
) -> list[PurchaseDetailResponse]:
    """由店长触发模拟任务，签收全部已达到预计时间的进货单。"""

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

    current_employee = await get_employee_by_id(employee_id=current_employee_id, db=db)
    if current_employee is None:
        raise HTTPException(
            status_code=http_status.HTTP_401_UNAUTHORIZED,
            detail="当前登录员工不存在",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not current_employee.is_active:
        raise HTTPException(status_code=http_status.HTTP_403_FORBIDDEN, detail="账号已停用")
    if current_employee.must_change_password:
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail="请先修改初始密码",
        )
    if current_employee.role != EmployeeRole.STORE_MANAGER:
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail="只有店长可以执行自动签收",
        )

    now = business_now()
    try:
        received = await auto_receive_due_purchases(
            arrived_at=now,
            employee_id=current_employee_id,
            db=db,
        )
        responses: list[PurchaseDetailResponse] = []
        for purchase in received:
            refreshed = await get_purchase_by_id(purchase_id=purchase.id, db=db)
            if refreshed is None:
                raise RuntimeError("已签收的进货单无法重新读取")
            # 复用详情服务现有的响应组装，确保详情与创建接口返回格式一致。
            responses.append(
                await get_purchase_detail_service(
                    purchase_id=refreshed.id,
                    current_employee_id=current_employee_id,
                    db=db,
                )
            )
        await db.commit()
        return responses
    except ValueError as error:
        await db.rollback()
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail=str(error),
        ) from error
    except IntegrityError as error:
        await db.rollback()
        raise HTTPException(
            status_code=http_status.HTTP_409_CONFLICT,
            detail="自动签收时发生数据冲突",
        ) from error


# endregion


# region 单张进货单手动签收
async def receive_purchase_service(
    purchase_id: int,
    current_employee_id: int,
    db: AsyncSession,
    *,
    http_request: Request | None = None,
) -> PurchaseDetailResponse:
    """只签收指定待到货订单；库存、批次、审计与状态在同一事务提交。"""

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

    employee = await get_employee_by_id(employee_id=current_employee_id, db=db)
    if employee is None:
        raise HTTPException(401, "当前登录员工不存在")
    if not employee.is_active or employee.must_change_password:
        raise HTTPException(403, "当前账号不可签收")
    if employee.role not in (EmployeeRole.STORE_MANAGER, EmployeeRole.REGULAR_EMPLOYEE):
        raise HTTPException(403, "只有店长或正式员工可以签收")
    purchase = await get_purchase_by_id(purchase_id=purchase_id, db=db)
    if purchase is None:
        raise HTTPException(404, "进货单不存在")
    if purchase.store_id != employee.store_id:
        raise HTTPException(403, "只能签收所属门店的进货单")
    if (
        employee.role == EmployeeRole.REGULAR_EMPLOYEE
        and employee.department_id != purchase.department_id
    ):
        raise HTTPException(403, "只能签收所属部门的进货单")
    if purchase.status != PurchaseStatus.PENDING:
        raise HTTPException(409, "进货单已经签收")
    try:
        received = await auto_receive_due_purchases(
            arrived_at=business_now(),
            employee_id=current_employee_id,
            db=db,
            only_purchase_id=purchase_id,
        )
        if not received:
            raise HTTPException(409, "进货单已被其他人签收")
        response = await get_purchase_detail_service(purchase_id, current_employee_id, db)
        await db.commit()
        return response
    except ValueError as error:
        await db.rollback()
        raise HTTPException(400, str(error)) from error
    except IntegrityError as error:
        await db.rollback()
        raise HTTPException(409, "签收入库时发生数据冲突") from error


# endregion


__all__ = [
    "auto_receive_purchases_service",
    "create_purchase_service",
    "get_purchase_detail_service",
    "get_purchases_list_service",
    "receive_purchase_service",
]


async def reject_manual_purchase_service(
    request: CreatePurchaseRequest,
    current_employee_id: int,
    db: AsyncSession,
    *,
    http_request: Request | None = None,
) -> ResponseModel[PurchaseDetailResponse]:
    """接收进货单汇总及商品明细，并返回进货单汇总及商品明细。"""
    raise HTTPException(409, "请保存订货计划，进货单将在截止时间自动生成")


async def create_purchase_records(
    purchase: CreatePurchaseRequest,
    created_by: int,
    db: AsyncSession,
    *,
    ordered_at_override: datetime | None = None,
) -> Purchase:
    """创建一张进货单及其全部进货明细，并发送到当前数据库事务。"""
    ordered_at = ordered_at_override or business_now()
    expected_arrival_at = ordered_at + timedelta(days=2)
    if purchase.expected_arrival_date is not None:
        expected_arrival_at = datetime.combine(purchase.expected_arrival_date, time(hour=12))
    purchase_no_prefix = f"PUR{ordered_at:%Y%m%d}"
    next_number = await next_business_sequence(f"purchase:{ordered_at:%Y%m%d}", db)
    purchase_no = f"{purchase_no_prefix}{next_number:04d}"
    supplier_product_ids_values_new = []
    for supplier_product_ids_item_item in purchase.items:
        supplier_product_ids_values_new.append(supplier_product_ids_item_item.supplier_product_id)
    supplier_product_ids = supplier_product_ids_values_new
    catalog_result = await data_access.get_order_catalog(
        db=db, supplier_product_ids=supplier_product_ids
    )
    catalog_products_mapping = {}
    for catalog_products_catalog_product in catalog_result.all():
        catalog_products_mapping[catalog_products_catalog_product.id] = (
            catalog_products_catalog_product
        )
    catalog_products = catalog_products_mapping
    missing_ids = sorted(set(supplier_product_ids) - catalog_products.keys())
    if missing_ids:
        missing_text = ", ".join(str(item_id) for item_id in missing_ids)
        raise ValueError(f"供应商商品目录不存在：{missing_text}")
    purchase_items: list[PurchaseItem] = []
    total_amount = Decimal("0.00")
    for requested_item in purchase.items:
        catalog_product = catalog_products[requested_item.supplier_product_id]
        subtotal = catalog_product.unit_cost * requested_item.quantity
        total_amount += subtotal
        production_date = requested_item.production_date
        if production_date is None:
            production_date = expected_arrival_at.date()
        expiration_date = requested_item.expiration_date
        if expiration_date is None:
            if catalog_product.shelf_life_days is None:
                raise ValueError(
                    f"供应商商品目录ID {catalog_product.id} 未设置默认保质期，无法自动计算到期日期"
                )
            expiration_date = production_date + timedelta(days=catalog_product.shelf_life_days)
        if expiration_date < production_date:
            raise ValueError(f"供应商商品目录ID {catalog_product.id} 的到期日期不能早于生产日期")
        product_id = None
        product_no_snapshot = None
        for existing_product in catalog_product.products:
            if existing_product.store_id == db.info.get("write_store_id", 1):
                product_id = existing_product.id
                product_no_snapshot = existing_product.product_no
                break
        purchase_items.append(
            PurchaseItem(
                store_id=db.info.get("write_store_id", 1),
                product_id=product_id,
                supplier_product_id=catalog_product.id,
                supplier_id=catalog_product.supplier_id,
                product_no_snapshot=product_no_snapshot,
                product_name_snapshot=catalog_product.name,
                supplier_name_snapshot=catalog_product.supplier.name,
                quantity=requested_item.quantity,
                unit_cost=catalog_product.unit_cost,
                subtotal=subtotal,
                production_date=production_date,
                expiration_date=expiration_date,
            )
        )
    if purchase.client_request_id:
        client_request_id_value = str(purchase.client_request_id)
    else:
        client_request_id_value = None
    new_purchase = Purchase(
        store_id=db.info.get("write_store_id", 1),
        purchase_no=purchase_no,
        client_request_id=client_request_id_value,
        department_id=purchase.department_id,
        created_by=created_by,
        received_by=None,
        ordered_at=ordered_at,
        expected_arrival_at=expected_arrival_at,
        arrived_at=None,
        total_amount=total_amount,
        status=PurchaseStatus.PENDING,
        items=purchase_items,
    )
    data_access.add_purchase_record(db=db, new_purchase=new_purchase)
    await db.flush()
    return new_purchase


async def auto_receive_due_purchases(
    arrived_at: datetime,
    employee_id: int | None,
    db: AsyncSession,
    only_purchase_id: int | None = None,
) -> list[Purchase]:
    """签收所有达到预计到货时间的待到货进货单，并同步商品与批次库存。"""
    due_purchases = list(
        (
            await data_access.get_due_purchases(
                db=db, arrived_at=arrived_at, only_purchase_id=only_purchase_id
            )
        ).all()
    )
    product_number = int(await data_access.get_latest_product_number(db=db) or 0)
    batch_number = int(await data_access.get_latest_batch_number(db=db, arrived_at=arrived_at) or 0)
    for purchase in due_purchases:
        if db.info.get("store_context"):
            if not await department_is_enabled(purchase.store_id, purchase.department_id, db):
                raise HTTPException(400, "本店未启用此部门")
        db.info["write_store_id"] = purchase.store_id
        if only_purchase_id is None:
            receiver = await data_access.get_default_receiving_employee(db=db, purchase=purchase)
        else:
            receiver = await data_access.get_manual_receiving_employee(
                db=db, employee_id=employee_id
            )
        if receiver is None:
            raise ValueError(f"部门ID {purchase.department_id} 没有可用的正式员工")
        for purchase_item in purchase.items:
            catalog_product = purchase_item.supplier_product
            product = await data_access.get_received_product(
                db=db, catalog_product=catalog_product, purchase=purchase
            )
            product_was_created = product is None
            if product is None:
                if catalog_product.category_id is None or catalog_product.category is None:
                    raise ValueError(f"供应商商品目录ID {catalog_product.id} 尚未设置商品分类")
                if catalog_product.category.department_id != purchase.department_id:
                    raise ValueError(f"供应商商品目录ID {catalog_product.id} 的分类不属于进货部门")
                product_number += 1
                product = Product(
                    store_id=purchase.store_id,
                    product_no="NEW" + uuid4().hex[:16],
                    name=catalog_product.name,
                    supplier_product_id=catalog_product.id,
                    department_id=purchase.department_id,
                    category_id=catalog_product.category_id,
                    purchase_price=purchase_item.unit_cost,
                    sale_price=purchase_item.unit_cost * Decimal("2"),
                    stock_quantity=0,
                    expiry_warning_days=1,
                    status=ProductStatus.ON_SALE,
                )
                data_access.add_received_product(db=db, product=product)
                await db.flush()
                product.product_no = f"P{product.id:05d}"
            before_product_stock = product.stock_quantity
            before_purchase_price = product.purchase_price
            product.purchase_price = purchase_item.unit_cost
            product.stock_quantity += purchase_item.quantity
            purchase_item.product_id = product.id
            batch_number += 1
            inventory_batch = InventoryBatch(
                store_id=purchase.store_id,
                batch_no="NEW" + uuid4().hex[:16],
                product_id=product.id,
                purchase_item_id=purchase_item.id,
                production_date=purchase_item.production_date,
                expiration_date=purchase_item.expiration_date,
                initial_quantity=purchase_item.quantity,
                remaining_quantity=purchase_item.quantity,
                status=InventoryBatchStatus.AVAILABLE,
                arrived_at=arrived_at,
            )
            data_access.add_received_batch(db=db, inventory_batch=inventory_batch)
            await db.flush()
            inventory_batch.batch_no = f"BAT{arrived_at:%Y%m%d}{inventory_batch.id:06d}"
            if product_was_created:
                action_value_item = "create_from_purchase"
            else:
                action_value_item = "increase_stock"
            if product_was_created:
                before_data_value = None
            else:
                before_data_value = {
                    "stock_quantity": before_product_stock,
                    "purchase_price": before_purchase_price,
                }
            await create_operation_audit_log(
                employee_id=employee_id,
                module="product",
                action=action_value_item,
                target_type="product",
                target_id=product.id,
                before_data=before_data_value,
                after_data={
                    "product_no": product.product_no,
                    "stock_quantity": product.stock_quantity,
                    "purchase_price": product.purchase_price,
                },
                reason="进货单签收入库",
                db=db,
            )
            await create_operation_audit_log(
                employee_id=employee_id,
                module="inventory",
                action="create_batch",
                target_type="inventory_batch",
                target_id=inventory_batch.id,
                before_data=None,
                after_data={
                    "batch_no": inventory_batch.batch_no,
                    "product_id": inventory_batch.product_id,
                    "purchase_item_id": inventory_batch.purchase_item_id,
                    "remaining_quantity": inventory_batch.remaining_quantity,
                    "expiration_date": inventory_batch.expiration_date,
                    "status": inventory_batch.status,
                },
                reason="进货单签收入库",
                db=db,
            )
        before_purchase_status = purchase.status
        purchase.received_by = receiver.id
        purchase.arrived_at = arrived_at
        purchase.status = PurchaseStatus.ARRIVED
        db.expire(purchase, ["received_by_employee"])
        if employee_id is None:
            action_value = "auto_receive"
        else:
            action_value = "manual_receive"
        if only_purchase_id is not None:
            reason_value = "单张进货单手动签收"
        else:
            if employee_id is None:
                reason_value = "系统按预计到货时间自动签收"
            else:
                reason_value = "店长手动补执行签收"
        await create_operation_audit_log(
            employee_id=employee_id,
            module="purchase",
            action=action_value,
            target_type="purchase",
            target_id=purchase.id,
            before_data={"status": before_purchase_status},
            after_data={
                "status": purchase.status,
                "received_by": purchase.received_by,
                "arrived_at": purchase.arrived_at,
            },
            reason=reason_value,
            db=db,
        )
    await db.flush()
    return due_purchases
