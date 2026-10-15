"""门店配置与全公司目录的数据访问。服务层负责权限，CRUD 明确执行数据库操作。"""

from sqlalchemy import func, select

from app.models.ai_pending_action import AiPendingAction
from app.models.category import Category
from app.models.department import Department
from app.models.employee import Employee
from app.models.enums import EmployeeRole, PurchaseStatus
from app.models.product import Product
from app.models.purchase import Purchase
from app.models.store import Store, StoreDepartment


async def first_active_store_id(db):
    statement = select(Store.id).where(Store.is_active.is_(True)).order_by(Store.id).limit(1)
    return await db.scalar(statement)


async def get_store_by_id(store_id, db):
    statement = select(Store).where(Store.id == store_id)
    return await db.scalar(statement)


async def department_is_enabled(store_id, department_id, db):
    """读取门店部门配置；是否允许操作由服务层判断。"""
    statement = select(StoreDepartment.is_active).where(
        StoreDepartment.store_id == store_id,
        StoreDepartment.department_id == department_id,
    )
    return bool(await db.scalar(statement))


async def get_headquarters_actor(db, employee_id):
    """执行require_headquarters所需的数据库查询；权限由调用它的服务检查。"""
    return await db.get(Employee, employee_id)


async def count_active_department_employees(db, department_id, store_id):
    """按明确的店铺、可选部门范围统计记录，服务层判断是否允许停用。"""
    statement = select(func.count(Employee.id)).where(
        Employee.store_id == store_id, Employee.is_active.is_(True)
    )
    if department_id is not None:
        statement = statement.where(Employee.department_id == department_id)
    return await db.scalar(statement)


async def count_department_stock_products(db, department_id, store_id):
    """按明确的店铺、可选部门范围统计记录，服务层判断是否允许停用。"""
    statement = select(func.count(Product.id)).where(
        Product.store_id == store_id, Product.stock_quantity > 0
    )
    if department_id is not None:
        statement = statement.where(Product.department_id == department_id)
    return await db.scalar(statement)


async def count_department_pending_purchases(db, department_id, store_id):
    """按明确的店铺、可选部门范围统计记录，服务层判断是否允许停用。"""
    statement = select(func.count(Purchase.id)).where(
        Purchase.store_id == store_id, Purchase.status == PurchaseStatus.PENDING
    )
    if department_id is not None:
        statement = statement.where(Purchase.department_id == department_id)
    return await db.scalar(statement)


async def get_assignment_store(db, store_id):
    """执行validate_assignment所需的数据库查询；权限由调用它的服务检查。"""
    return await db.get(Store, store_id)


async def get_assignment_store_department(db, department_id, store_id):
    """执行validate_assignment所需的数据库查询；权限由调用它的服务检查。"""
    return await db.get(StoreDepartment, (store_id, department_id))


async def get_assignment_department(db, department_id):
    """执行validate_assignment所需的数据库查询；权限由调用它的服务检查。"""
    return await db.get(Department, department_id)


async def get_store_list_actor(db, employee_id):
    """执行list_stores_service所需的数据库查询；权限由调用它的服务检查。"""
    return await db.get(Employee, employee_id)


async def get_visible_stores(db, employee):
    """构建并执行list_stores_query的查询，店铺条件在这里明确添加。"""
    statement = select(Store).order_by(Store.id)
    if employee.role != EmployeeRole.HEADQUARTERS:
        statement = statement.where(Store.is_active.is_(True))
    return await db.scalars(statement)


async def get_company_catalog_actor(db, employee_id):
    """执行company_data_service所需的数据库查询；权限由调用它的服务检查。"""
    return await db.get(Employee, employee_id)


async def get_company_departments(db):
    """执行company_data_service所需的数据库查询；权限由调用它的服务检查。"""
    return await db.scalars(select(Department))


async def get_company_categories(db):
    """执行company_data_service所需的数据库查询；权限由调用它的服务检查。"""
    return await db.scalars(select(Category))


async def get_company_employees(db):
    """执行company_data_service所需的数据库查询；权限由调用它的服务检查。"""
    return await db.scalars(select(Employee).order_by(Employee.id))


async def get_store_departments(db, store_id):
    """执行store_departments_service所需的数据库查询或更新；权限由调用它的服务检查。"""
    return await db.execute(
        select(Department, StoreDepartment.is_active).outerjoin(
            StoreDepartment,
            (StoreDepartment.department_id == Department.id)
            & (StoreDepartment.store_id == store_id),
        )
    )


def add_store(db, store):
    """执行create_store_service所需的数据库新增；权限由调用它的服务检查。"""
    return db.add(store)


def add_enabled_store_department(db, department_id, store):
    """执行create_store_service所需的数据库新增；权限由调用它的服务检查。"""
    return db.add(StoreDepartment(store_id=store.id, department_id=department_id, is_active=True))


async def get_department_to_enable(db, department_id):
    """执行create_store_service所需的数据库查询；权限由调用它的服务检查。"""
    return await db.get(Department, department_id)


async def get_store_for_update(db, store_id):
    """执行update_store_service所需的数据库查询；权限由调用它的服务检查。"""
    return await db.scalar(select(Store).where(Store.id == store_id).with_for_update())


async def get_department_store_for_update(db, store_id):
    """执行enable_department_service所需的数据库查询；权限由调用它的服务检查。"""
    return await db.scalar(select(Store).where(Store.id == store_id).with_for_update())


async def get_department_to_configure(db, department_id):
    """执行enable_department_service所需的数据库查询；权限由调用它的服务检查。"""
    return await db.get(Department, department_id)


async def get_store_department_config(db, department_id, store_id):
    """执行enable_department_service所需的数据库查询；权限由调用它的服务检查。"""
    return await db.get(StoreDepartment, (store_id, department_id))


def add_store_department_config(db, config):
    """执行enable_department_service所需的数据库新增；权限由调用它的服务检查。"""
    return db.add(config)


async def get_transfer_employee_for_update(db, target_id):
    """执行transfer_employee_service所需的数据库查询；权限由调用它的服务检查。"""
    return await db.scalar(select(Employee).where(Employee.id == target_id).with_for_update())


async def get_employee_pending_actions(db, target):
    """执行transfer_employee_service所需的数据库查询；权限由调用它的服务检查。"""
    return await db.scalars(
        select(AiPendingAction).where(
            AiPendingAction.employee_id == target.id, AiPendingAction.status == "pending"
        )
    )


def add_company_department(db, item):
    """执行company_department_service所需的数据库新增；权限由调用它的服务检查。"""
    return db.add(item)


async def get_company_department(db, record_id):
    """执行company_department_service所需的数据库查询；权限由调用它的服务检查。"""
    return await db.get(Department, record_id)


async def get_all_store_ids(db):
    """执行company_department_service所需的数据库查询；权限由调用它的服务检查。"""
    return await db.scalars(select(Store.id))


def add_company_category(db, item):
    """执行company_category_service所需的数据库新增；权限由调用它的服务检查。"""
    return db.add(item)


async def get_category_department(db, request):
    """执行company_category_service所需的数据库查询；权限由调用它的服务检查。"""
    return await db.get(Department, request.department_id)


async def get_company_category(db, record_id):
    """执行company_category_service所需的数据库查询；权限由调用它的服务检查。"""
    return await db.get(Category, record_id)


async def get_category_product_reference(db, record_id):
    """分类是全公司共用的，因此检查所有店铺是否有商品引用该分类。"""
    statement = select(Product.id).where(Product.category_id == record_id).limit(1)
    return await db.scalar(statement)
