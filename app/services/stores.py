"""stores：业务规则和响应组装。"""

from uuid import uuid4

from fastapi import HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import (
    CATEGORIES_CACHE_NAMESPACE,
    DEPARTMENTS_CACHE_NAMESPACE,
    clear_cache_namespaces,
)
from app.core.security import hash_password
from app.crud import stores as data_access
from app.crud.auth import get_employee_by_id
from app.crud.employees import create_employee
from app.crud.operation_audit_logs import create_operation_audit_log
from app.crud.stores import first_active_store_id, get_store_by_id
from app.models.category import Category
from app.models.department import Department
from app.models.enums import EmployeeRole
from app.models.store import Store, StoreDepartment
from app.schemas.base import ResponseModel
from app.schemas.stores import (
    CompanyCategoryRequest,
    CompanyDepartmentRequest,
    EmployeeTransferRequest,
    HeadquartersEmployeeCreateRequest,
    StoreDepartmentRequest,
    StoreWriteRequest,
)


async def require_headquarters(employee_id, db):
    employee = await data_access.get_headquarters_actor(db=db, employee_id=employee_id)
    if employee is None:
        raise HTTPException(401, "当前登录员工不存在")
    if employee is None or employee.role != EmployeeRole.HEADQUARTERS:
        raise HTTPException(403, "只有总部可以执行此操作")
    return employee


async def log_change(
    employee_id, action, target_type, target_id, before, after, reason, db, store_id=None
):
    await create_operation_audit_log(
        employee_id=employee_id,
        module="company",
        action=action,
        target_type=target_type,
        target_id=target_id,
        before_data=before,
        after_data=after,
        reason=reason,
        db=db,
        store_id=store_id,
    )


def store_data(store):
    return {
        "id": store.id,
        "store_no": store.store_no,
        "name": store.name,
        "address": store.address,
        "phone": store.phone,
        "is_active": store.is_active,
        "timezone": store.timezone,
    }


async def check_department_can_disable(store_id, department_id, db):
    """先逐项检查阻止停用的业务数据，再允许门店或部门停用。"""
    active_employee_count = await data_access.count_active_department_employees(
        db=db, department_id=department_id, store_id=store_id
    )
    if active_employee_count:
        raise HTTPException(409, "仍有启用员工，请先处理")

    stock_product_count = await data_access.count_department_stock_products(
        db=db, department_id=department_id, store_id=store_id
    )
    if stock_product_count:
        raise HTTPException(409, "仍有剩余库存，请先处理")

    pending_purchase_count = await data_access.count_department_pending_purchases(
        db=db, department_id=department_id, store_id=store_id
    )
    if pending_purchase_count:
        raise HTTPException(409, "仍有待签收进货单，请先处理")


async def validate_assignment(store_id, department_id, role, db):
    if role == EmployeeRole.HEADQUARTERS:
        if store_id is not None or department_id is not None:
            raise HTTPException(400, "总部账号不绑定门店和部门")
        return
    if store_id:
        store = await data_access.get_assignment_store(db=db, store_id=store_id)
    else:
        store = None
    if store is None or not store.is_active:
        raise HTTPException(400, "请选择启用门店")
    if role != EmployeeRole.STORE_MANAGER and department_id is None:
        raise HTTPException(400, "员工必须选择本店启用的部门")
    if department_id is not None:
        config = await data_access.get_assignment_store_department(
            db=db, department_id=department_id, store_id=store_id
        )
        department = await data_access.get_assignment_department(db=db, department_id=department_id)
        if not config or not config.is_active or (not department) or (not department.is_active):
            raise HTTPException(400, "目标门店未启用此部门")


async def list_stores_service(
    employee_id: int, db: AsyncSession, *, http_request: Request | None = None
):

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
            company_management=True,
            company_catalog_read=True,
            private_employee_path=False,
            store_context=True,
        )
        http_request.state.store_id = selected_store_id
        http_request.state.employee_id = access_employee.id
        http_request.state.own_store_id = access_employee.store_id

    employee = await data_access.get_store_list_actor(db=db, employee_id=employee_id)
    if employee is None:
        raise HTTPException(401, "当前登录员工不存在")
    data_value_values = []
    for data_value_store in (await data_access.get_visible_stores(db=db, employee=employee)).all():
        data_value_values.append(store_data(data_value_store))
    data_value = data_value_values
    return ResponseModel(data=data_value)


async def company_data_service(
    employee_id: int, db: AsyncSession, *, http_request: Request | None = None
):

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
            company_management=True,
            company_catalog_read=True,
            private_employee_path=False,
            store_context=True,
        )
        http_request.state.store_id = selected_store_id
        http_request.state.employee_id = access_employee.id
        http_request.state.own_store_id = access_employee.store_id

    employee = await data_access.get_company_catalog_actor(db=db, employee_id=employee_id)
    if employee is None:
        raise HTTPException(401, "当前登录员工不存在")
    departments_values = []
    for departments_item in (await data_access.get_company_departments(db=db)).all():
        departments_values.append(
            {
                "id": departments_item.id,
                "name": departments_item.name,
                "code": departments_item.code,
                "is_active": departments_item.is_active,
            }
        )
    departments = departments_values
    categories_values = []
    for categories_item in (await data_access.get_company_categories(db=db)).all():
        categories_values.append(
            {
                "id": categories_item.id,
                "name": categories_item.name,
                "department_id": categories_item.department_id,
                "is_active": categories_item.is_active,
            }
        )
    categories = categories_values
    employees = []
    if employee.role == EmployeeRole.HEADQUARTERS:
        employees_values = []
        for employees_item in (await data_access.get_company_employees(db=db)).all():
            employees_values.append(
                {
                    "id": employees_item.id,
                    "name": employees_item.name,
                    "employee_no": employees_item.employee_no,
                    "store_id": employees_item.store_id,
                    "department_id": employees_item.department_id,
                    "role": employees_item.role,
                }
            )
        employees = employees_values
    return ResponseModel(
        data={"departments": departments, "categories": categories, "employees": employees}
    )


async def store_departments_service(
    store_id: int, employee_id: int, db: AsyncSession, *, http_request: Request | None = None
):

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
            company_management=True,
            company_catalog_read=True,
            private_employee_path=False,
            store_context=True,
        )
        http_request.state.store_id = selected_store_id
        http_request.state.employee_id = access_employee.id
        http_request.state.own_store_id = access_employee.store_id

    rows = (await data_access.get_store_departments(db=db, store_id=store_id)).all()
    data_value_item_values = []
    for data_value_item_item, data_value_item_active in rows:
        data_value_item_values.append(
            {
                "id": data_value_item_item.id,
                "name": data_value_item_item.name,
                "is_active": bool(data_value_item_active) and data_value_item_item.is_active,
            }
        )
    data_value_item = data_value_item_values
    return ResponseModel(data=data_value_item)


async def create_store_service(
    request: StoreWriteRequest,
    employee_id: int,
    db: AsyncSession,
    *,
    http_request: Request | None = None,
):
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
            company_management=True,
            company_catalog_read=True,
            private_employee_path=False,
            store_context=True,
        )
        http_request.state.store_id = selected_store_id
        http_request.state.employee_id = access_employee.id
        http_request.state.own_store_id = access_employee.store_id
    await require_headquarters(employee_id, db)
    store = Store(
        store_no="NEW" + uuid4().hex[:16],
        name=request.name,
        address=request.address,
        phone=request.phone,
        is_active=request.is_active,
    )
    data_access.add_store(db=db, store=store)
    await db.flush()
    store.store_no = f"DP{store.id:04d}"
    for department_id in set(request.department_ids):
        department = await data_access.get_department_to_enable(db=db, department_id=department_id)
        if department is None or not department.is_active:
            raise HTTPException(400, "启用部门不存在或已停用")
        data_access.add_enabled_store_department(db=db, department_id=department_id, store=store)
    await log_change(
        employee_id,
        "create_store",
        "store",
        store.id,
        None,
        store_data(store),
        request.reason,
        db,
        store.id,
    )
    await db.commit()
    return ResponseModel(data=store_data(store))


async def update_store_service(
    store_id: int,
    request: StoreWriteRequest,
    employee_id: int,
    db: AsyncSession,
    *,
    http_request: Request | None = None,
):

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
            company_management=True,
            company_catalog_read=True,
            private_employee_path=False,
            store_context=True,
        )
        http_request.state.store_id = selected_store_id
        http_request.state.employee_id = access_employee.id
        http_request.state.own_store_id = access_employee.store_id

    await require_headquarters(employee_id, db)
    store = await data_access.get_store_for_update(db=db, store_id=store_id)
    if store is None:
        raise HTTPException(404, "门店不存在")
    if not request.is_active and store.is_active:
        await check_department_can_disable(store_id, None, db)
    before = store_data(store)
    store.name, store.address, store.phone, store.is_active = (
        request.name,
        request.address,
        request.phone,
        request.is_active,
    )
    await log_change(
        employee_id,
        "update_store",
        "store",
        store.id,
        before,
        store_data(store),
        request.reason,
        db,
        store.id,
    )
    await db.commit()
    return ResponseModel(data=store_data(store))


async def enable_department_service(
    store_id: int,
    department_id: int,
    request: StoreDepartmentRequest,
    employee_id: int,
    db: AsyncSession,
    *,
    http_request: Request | None = None,
):

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
            company_management=True,
            company_catalog_read=True,
            private_employee_path=False,
            store_context=True,
        )
        http_request.state.store_id = selected_store_id
        http_request.state.employee_id = access_employee.id
        http_request.state.own_store_id = access_employee.store_id

    await require_headquarters(employee_id, db)
    store = await data_access.get_department_store_for_update(db=db, store_id=store_id)
    department = await data_access.get_department_to_configure(db=db, department_id=department_id)
    if store is None or department is None or (request.is_active and (not department.is_active)):
        raise HTTPException(400, "门店或启用部门无效")
    if not request.is_active:
        await check_department_can_disable(store_id, department_id, db)
    config = await data_access.get_store_department_config(
        db=db, department_id=department_id, store_id=store_id
    )
    if config:
        is_active_value = config.is_active
    else:
        is_active_value = False
    before = {"is_active": is_active_value}
    if config is None:
        config = StoreDepartment(store_id=store_id, department_id=department_id)
        data_access.add_store_department_config(db=db, config=config)
    config.is_active = request.is_active
    await log_change(
        employee_id,
        "configure_department",
        "store",
        store_id,
        before,
        {"department_id": department_id, "is_active": request.is_active},
        request.reason,
        db,
        store_id,
    )
    await db.commit()
    await clear_cache_namespaces(DEPARTMENTS_CACHE_NAMESPACE, CATEGORIES_CACHE_NAMESPACE)
    return ResponseModel(data={"is_active": config.is_active})


async def transfer_employee_service(
    target_id: int,
    request: EmployeeTransferRequest,
    employee_id: int,
    db: AsyncSession,
    *,
    http_request: Request | None = None,
):

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
            company_management=True,
            company_catalog_read=True,
            private_employee_path=False,
            store_context=True,
        )
        http_request.state.store_id = selected_store_id
        http_request.state.employee_id = access_employee.id
        http_request.state.own_store_id = access_employee.store_id

    await require_headquarters(employee_id, db)
    target = await data_access.get_transfer_employee_for_update(db=db, target_id=target_id)
    if target is None:
        raise HTTPException(404, "员工不存在")
    role = request.role or target.role
    await validate_assignment(request.store_id, request.department_id, role, db)
    if target_id == employee_id and role != EmployeeRole.HEADQUARTERS:
        raise HTTPException(400, "不能撤销自己的总部权限")
    before = {
        "store_id": target.store_id,
        "department_id": target.department_id,
        "role": target.role,
    }
    target.store_id, target.department_id, target.role = (
        request.store_id,
        request.department_id,
        role,
    )
    actions = (await data_access.get_employee_pending_actions(db=db, target=target)).all()
    for action in actions:
        action.status = "cancelled"
        action.failure_reason = "员工异动后需重新发起操作"
    await log_change(
        employee_id,
        "transfer_employee",
        "employee",
        target.id,
        before,
        {"store_id": target.store_id, "department_id": target.department_id, "role": target.role},
        request.reason,
        db,
        request.store_id,
    )
    await db.commit()
    return ResponseModel(
        data={
            "id": target.id,
            "store_id": target.store_id,
            "department_id": target.department_id,
            "role": target.role,
        }
    )


async def headquarters_create_employee_service(
    request: HeadquartersEmployeeCreateRequest,
    employee_id: int,
    db: AsyncSession,
    *,
    http_request: Request | None = None,
):

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
            company_management=True,
            company_catalog_read=True,
            private_employee_path=False,
            store_context=True,
        )
        http_request.state.store_id = selected_store_id
        http_request.state.employee_id = access_employee.id
        http_request.state.own_store_id = access_employee.store_id

    await require_headquarters(employee_id, db)
    await validate_assignment(request.store_id, request.department_id, request.role, db)
    temporary_password = "MF" + uuid4().hex[:14]
    employee = await create_employee(
        name=request.name,
        role=request.role,
        department_id=request.department_id,
        password_hash=hash_password(temporary_password),
        db=db,
        store_id=request.store_id,
    )
    await log_change(
        employee_id,
        "create_employee",
        "employee",
        employee.id,
        None,
        {"name": employee.name, "store_id": employee.store_id, "role": employee.role},
        request.reason,
        db,
        request.store_id,
    )
    await db.commit()
    return ResponseModel(
        data={
            "id": employee.id,
            "employee_no": employee.employee_no,
            "temporary_password": temporary_password,
        }
    )


async def company_department_service(
    request: CompanyDepartmentRequest,
    record_id: int | None,
    employee_id: int,
    db: AsyncSession,
    *,
    http_request: Request | None = None,
):
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
            company_management=True,
            company_catalog_read=True,
            private_employee_path=False,
            store_context=True,
        )
        http_request.state.store_id = selected_store_id
        http_request.state.employee_id = access_employee.id
        http_request.state.own_store_id = access_employee.store_id
    await require_headquarters(employee_id, db)
    if record_id:
        item = await data_access.get_company_department(db=db, record_id=record_id)
    else:
        item = Department()
    if item is None:
        raise HTTPException(404, "部门不存在")
    if not request.is_active:
        for store_id in (await data_access.get_all_store_ids(db=db)).all():
            await check_department_can_disable(store_id, record_id, db)
    item.code, item.name, item.is_active = (request.code, request.name, request.is_active)
    data_access.add_company_department(db=db, item=item)
    await db.flush()
    await log_change(
        employee_id,
        "maintain_department",
        "department",
        item.id,
        None,
        request.model_dump(),
        None,
        db,
    )
    await db.commit()
    await clear_cache_namespaces(DEPARTMENTS_CACHE_NAMESPACE, CATEGORIES_CACHE_NAMESPACE)
    return ResponseModel(data={"id": item.id, "name": item.name})


async def company_category_service(
    request: CompanyCategoryRequest,
    record_id: int | None,
    employee_id: int,
    db: AsyncSession,
    *,
    http_request: Request | None = None,
):
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
            company_management=True,
            company_catalog_read=True,
            private_employee_path=False,
            store_context=True,
        )
        http_request.state.store_id = selected_store_id
        http_request.state.employee_id = access_employee.id
        http_request.state.own_store_id = access_employee.store_id
    await require_headquarters(employee_id, db)
    department = await data_access.get_category_department(db=db, request=request)
    if not department or not department.is_active:
        raise HTTPException(400, "部门不存在或已停用")
    if record_id:
        item = await data_access.get_company_category(db=db, record_id=record_id)
    else:
        item = Category()
    if item is None:
        raise HTTPException(404, "分类不存在")
    if record_id and item.department_id != request.department_id:
        referenced = await data_access.get_category_product_reference(db=db, record_id=record_id)
        if referenced is not None:
            raise HTTPException(409, "已有商品使用此分类，不能修改所属部门")
    item.name, item.department_id, item.is_active = (
        request.name,
        request.department_id,
        request.is_active,
    )
    data_access.add_company_category(db=db, item=item)
    await db.flush()
    await log_change(
        employee_id, "maintain_category", "category", item.id, None, request.model_dump(), None, db
    )
    await db.commit()
    await clear_cache_namespaces(CATEGORIES_CACHE_NAMESPACE)
    return ResponseModel(data={"id": item.id, "name": item.name})
