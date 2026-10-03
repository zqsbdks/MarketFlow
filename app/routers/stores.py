"""所有员工可查询门店，总部独占门店配置、统一目录和员工异动权限。"""

from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import (
    CATEGORIES_CACHE_NAMESPACE,
    DEPARTMENTS_CACHE_NAMESPACE,
    clear_cache_namespaces,
)
from app.core.security import hash_password
from app.crud.employees import create_employee
from app.crud.operation_audit_logs import create_operation_audit_log
from app.dependencies.auth import get_verified_current_employee_id
from app.dependencies.db import get_db
from app.models.ai_pending_action import AiPendingAction
from app.models.category import Category
from app.models.department import Department
from app.models.employee import Employee
from app.models.enums import EmployeeRole, PurchaseStatus
from app.models.product import Product
from app.models.purchase import Purchase
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

stores_router = APIRouter(prefix="/stores", tags=["stores"])


async def require_headquarters(employee_id, db):
    employee = await db.get(Employee, employee_id)
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


# region 门店查询与维护
@stores_router.get("", summary="查询可查看的门店")
async def list_stores(
    employee_id: int = Depends(get_verified_current_employee_id), db: AsyncSession = Depends(get_db)
):
    statement = select(Store).order_by(Store.id)
    employee = await db.get(Employee, employee_id)
    if employee is None:
        raise HTTPException(401, "当前登录员工不存在")
    if employee.role != EmployeeRole.HEADQUARTERS:
        statement = statement.where(Store.is_active.is_(True))
    return ResponseModel(data=[store_data(store) for store in (await db.scalars(statement)).all()])


@stores_router.get("/company-data", summary="查询统一部门、分类及总部可管理的员工")
async def company_data(
    employee_id: int = Depends(get_verified_current_employee_id), db: AsyncSession = Depends(get_db)
):
    employee = await db.get(Employee, employee_id)
    if employee is None:
        raise HTTPException(401, "当前登录员工不存在")
    departments = [
        {"id": item.id, "name": item.name, "code": item.code, "is_active": item.is_active}
        for item in (await db.scalars(select(Department))).all()
    ]
    categories = [
        {
            "id": item.id,
            "name": item.name,
            "department_id": item.department_id,
            "is_active": item.is_active,
        }
        for item in (await db.scalars(select(Category))).all()
    ]
    employees = []
    if employee.role == EmployeeRole.HEADQUARTERS:
        employees = [
            {
                "id": item.id,
                "name": item.name,
                "employee_no": item.employee_no,
                "store_id": item.store_id,
                "department_id": item.department_id,
                "role": item.role,
            }
            for item in (await db.scalars(select(Employee).order_by(Employee.id))).all()
        ]
    return ResponseModel(
        data={"departments": departments, "categories": categories, "employees": employees}
    )


@stores_router.get("/{store_id}/departments", summary="查询门店部门启用配置")
async def store_departments(
    store_id: int,
    employee_id: int = Depends(get_verified_current_employee_id),
    db: AsyncSession = Depends(get_db),
):
    rows = (
        await db.execute(
            select(Department, StoreDepartment.is_active).outerjoin(
                StoreDepartment,
                (StoreDepartment.department_id == Department.id)
                & (StoreDepartment.store_id == store_id),
            )
        )
    ).all()
    return ResponseModel(
        data=[
            {"id": item.id, "name": item.name, "is_active": bool(active) and item.is_active}
            for item, active in rows
        ]
    )


@stores_router.post("", summary="总部创建门店")
async def create_store(
    request: StoreWriteRequest,
    employee_id: int = Depends(get_verified_current_employee_id),
    db: AsyncSession = Depends(get_db),
):
    await require_headquarters(employee_id, db)
    store = Store(
        store_no="NEW" + uuid4().hex[:16],
        name=request.name,
        address=request.address,
        phone=request.phone,
        is_active=request.is_active,
    )
    db.add(store)
    await db.flush()
    store.store_no = f"DP{store.id:04d}"
    for department_id in set(request.department_ids):
        department = await db.get(Department, department_id)
        if department is None or not department.is_active:
            raise HTTPException(400, "启用部门不存在或已停用")
        db.add(StoreDepartment(store_id=store.id, department_id=department_id, is_active=True))
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


async def check_department_can_disable(store_id, department_id, db):
    staff = select(func.count(Employee.id)).where(
        Employee.store_id == store_id, Employee.is_active.is_(True)
    )
    stock = select(func.count(Product.id)).where(
        Product.store_id == store_id, Product.stock_quantity > 0
    )
    pending = select(func.count(Purchase.id)).where(
        Purchase.store_id == store_id, Purchase.status == PurchaseStatus.PENDING
    )
    if department_id is not None:
        staff = staff.where(Employee.department_id == department_id)
        stock = stock.where(Product.department_id == department_id)
        pending = pending.where(Purchase.department_id == department_id)
    previous = db.info.get("read_store_id")
    db.info["read_store_id"] = store_id
    try:
        if await db.scalar(staff) or await db.scalar(stock) or await db.scalar(pending):
            raise HTTPException(409, "仍有启用员工、剩余库存或待签收进货单，请先处理")
    finally:
        db.info["read_store_id"] = previous


@stores_router.put("/{store_id}", summary="总部修改门店")
async def update_store(
    store_id: int,
    request: StoreWriteRequest,
    employee_id: int = Depends(get_verified_current_employee_id),
    db: AsyncSession = Depends(get_db),
):
    await require_headquarters(employee_id, db)
    store = await db.scalar(select(Store).where(Store.id == store_id).with_for_update())
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


@stores_router.put("/{store_id}/departments/{department_id}", summary="总部设置门店启用部门")
async def enable_department(
    store_id: int,
    department_id: int,
    request: StoreDepartmentRequest,
    employee_id: int = Depends(get_verified_current_employee_id),
    db: AsyncSession = Depends(get_db),
):
    await require_headquarters(employee_id, db)
    store = await db.scalar(select(Store).where(Store.id == store_id).with_for_update())
    department = await db.get(Department, department_id)
    if store is None or department is None or (request.is_active and not department.is_active):
        raise HTTPException(400, "门店或启用部门无效")
    if not request.is_active:
        await check_department_can_disable(store_id, department_id, db)
    config = await db.get(StoreDepartment, (store_id, department_id))
    before = {"is_active": config.is_active if config else False}
    if config is None:
        config = StoreDepartment(store_id=store_id, department_id=department_id)
        db.add(config)
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


# endregion


# region 员工调店和角色任命
async def validate_assignment(store_id, department_id, role, db):
    if role == EmployeeRole.HEADQUARTERS:
        if store_id is not None or department_id is not None:
            raise HTTPException(400, "总部账号不绑定门店和部门")
        return
    store = await db.get(Store, store_id) if store_id else None
    if store is None or not store.is_active:
        raise HTTPException(400, "请选择启用门店")
    if role != EmployeeRole.STORE_MANAGER and department_id is None:
        raise HTTPException(400, "员工必须选择本店启用的部门")
    if department_id is not None:
        config = await db.get(StoreDepartment, (store_id, department_id))
        department = await db.get(Department, department_id)
        if not config or not config.is_active or not department or not department.is_active:
            raise HTTPException(400, "目标门店未启用此部门")


@stores_router.put("/employees/{target_id}/assignment", summary="仅总部可以调店及任命店长")
async def transfer_employee(
    target_id: int,
    request: EmployeeTransferRequest,
    employee_id: int = Depends(get_verified_current_employee_id),
    db: AsyncSession = Depends(get_db),
):
    await require_headquarters(employee_id, db)
    target = await db.scalar(select(Employee).where(Employee.id == target_id).with_for_update())
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
    actions = (
        await db.scalars(
            select(AiPendingAction).where(
                AiPendingAction.employee_id == target.id, AiPendingAction.status == "pending"
            )
        )
    ).all()
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


@stores_router.post("/employees", summary="总部创建门店店长或其他员工账号")
async def headquarters_create_employee(
    request: HeadquartersEmployeeCreateRequest,
    employee_id: int = Depends(get_verified_current_employee_id),
    db: AsyncSession = Depends(get_db),
):
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


# endregion


# region 全公司统一部门分类
@stores_router.post("/company-departments", summary="总部创建统一部门")
@stores_router.put("/company-departments/{record_id}", summary="总部修改统一部门")
async def company_department(
    request: CompanyDepartmentRequest,
    record_id: int | None = None,
    employee_id: int = Depends(get_verified_current_employee_id),
    db: AsyncSession = Depends(get_db),
):
    await require_headquarters(employee_id, db)
    item = await db.get(Department, record_id) if record_id else Department()
    if item is None:
        raise HTTPException(404, "部门不存在")
    if not request.is_active:
        for store_id in (await db.scalars(select(Store.id))).all():
            await check_department_can_disable(store_id, record_id, db)
    item.code, item.name, item.is_active = request.code, request.name, request.is_active
    db.add(item)
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


@stores_router.post("/company-categories", summary="总部创建统一分类")
@stores_router.put("/company-categories/{record_id}", summary="总部修改统一分类")
async def company_category(
    request: CompanyCategoryRequest,
    record_id: int | None = None,
    employee_id: int = Depends(get_verified_current_employee_id),
    db: AsyncSession = Depends(get_db),
):
    await require_headquarters(employee_id, db)
    department = await db.get(Department, request.department_id)
    if not department or not department.is_active:
        raise HTTPException(400, "部门不存在或已停用")
    item = await db.get(Category, record_id) if record_id else Category()
    if item is None:
        raise HTTPException(404, "分类不存在")
    # 分类是全公司共用的；已有商品引用时迁移部门会让这些商品的部门与分类不一致。
    if record_id and item.department_id != request.department_id:
        referenced = await db.scalar(
            select(Product.id).where(Product.category_id == record_id).limit(1)
        )
        if referenced is not None:
            raise HTTPException(409, "已有商品使用此分类，不能修改所属部门")
    item.name, item.department_id, item.is_active = (
        request.name,
        request.department_id,
        request.is_active,
    )
    db.add(item)
    await db.flush()
    await log_change(
        employee_id, "maintain_category", "category", item.id, None, request.model_dump(), None, db
    )
    await db.commit()
    await clear_cache_namespaces(CATEGORIES_CACHE_NAMESPACE)
    return ResponseModel(data={"id": item.id, "name": item.name})


# endregion
