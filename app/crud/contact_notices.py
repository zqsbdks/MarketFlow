"""联络事项查询与行锁；接收范围使用发布时保存的员工名单。"""

from sqlalchemy import delete, exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.business_time import business_now
from app.models.contact_notice import ContactNotice, ContactNoticeRecipient
from app.models.department import Department
from app.models.employee import Employee
from app.models.enums import EmployeeRole
from app.models.store import Store, StoreDepartment


# region 查询事项和接收名单
async def get_notice(notice_id: int, db: AsyncSession, *, lock: bool = False):
    statement = select(ContactNotice).where(ContactNotice.id == notice_id)
    if lock:
        statement = statement.with_for_update().execution_options(populate_existing=True)
    return await db.scalar(statement)


async def get_recipients(notice_id: int, db: AsyncSession):
    statement = (
        select(ContactNoticeRecipient, Employee.name, Department.name)
        .join(Employee, Employee.id == ContactNoticeRecipient.employee_id)
        .outerjoin(Department, Department.id == Employee.department_id)
        .where(ContactNoticeRecipient.notice_id == notice_id)
        .order_by(Employee.department_id, Employee.id)
    )
    if (
        db.info.get("private_employee_path")
        and db.info.get("actor_role") != EmployeeRole.HEADQUARTERS
    ):
        statement = statement.where(Employee.store_id == db.info["own_store_id"])
    return (await db.execute(statement)).all()


async def get_notices(request, employee, now, db: AsyncSession):
    """在当前账号可见范围内分页读取事项，应用收件/发布/管理视角与筛选条件。

    权限范围必须先由服务层验证；分页总数与记录使用一致条件，避免泄露不可见事项。"""
    conditions = []
    recipient = exists().where(
        ContactNoticeRecipient.notice_id == ContactNotice.id,
        ContactNoticeRecipient.employee_id == employee.id,
        ContactNoticeRecipient.store_id == employee.store_id,
    )
    if request.view == "received":
        conditions.extend(
            [
                recipient,
                ContactNotice.status.in_(["published", "closed"]),
                ContactNotice.starts_at <= now,
            ]
        )
    elif request.view == "published":
        conditions.append(ContactNotice.publisher_id == employee.id)
    if employee.role != EmployeeRole.HEADQUARTERS:
        if request.view == "management":
            own_recipients = exists().where(
                ContactNoticeRecipient.notice_id == ContactNotice.id,
                ContactNoticeRecipient.store_id == employee.store_id,
            )
            conditions.append(
                or_(
                    ContactNotice.store_id == employee.store_id,
                    (ContactNotice.source == "headquarters") & own_recipients,
                )
            )
        else:
            conditions.append(
                or_(
                    ContactNotice.store_id == employee.store_id,
                    ContactNotice.source == "headquarters",
                )
            )
    if request.source:
        conditions.append(ContactNotice.source == request.source)
    if request.target_type:
        conditions.append(ContactNotice.target_type == request.target_type)
    if request.status:
        conditions.append(ContactNotice.status == request.status)
    if request.keyword:
        conditions.append(
            or_(
                ContactNotice.title.ilike(f"%{request.keyword}%"),
                ContactNotice.content.ilike(f"%{request.keyword}%"),
            )
        )
    if request.priority:
        conditions.append(ContactNotice.priority == request.priority)
    if request.department_id is not None:
        conditions.append(ContactNotice.department_id == request.department_id)
    if request.publisher_id is not None:
        conditions.append(ContactNotice.publisher_id == request.publisher_id)
    if request.start_time is not None:
        conditions.append(ContactNotice.created_at >= request.start_time)
    if request.end_time is not None:
        conditions.append(ContactNotice.created_at <= request.end_time)
    if request.overdue is True:
        conditions.append(ContactNotice.deadline_at <= now)
    elif request.overdue is False:
        conditions.append(or_(ContactNotice.deadline_at.is_(None), ContactNotice.deadline_at > now))
    if request.read is not None:
        read_condition = select(ContactNoticeRecipient.id).where(
            ContactNoticeRecipient.notice_id == ContactNotice.id,
            ContactNoticeRecipient.employee_id == employee.id,
        )
        if request.read:
            read_condition = read_condition.where(ContactNoticeRecipient.read_at.is_not(None))
        else:
            read_condition = read_condition.where(ContactNoticeRecipient.read_at.is_(None))
        conditions.append(read_condition.exists())
    if request.confirmed is not None:
        confirmation = select(ContactNoticeRecipient.id).where(
            ContactNoticeRecipient.notice_id == ContactNotice.id,
            ContactNoticeRecipient.employee_id == employee.id,
        )
        if request.confirmed:
            confirmation = confirmation.where(ContactNoticeRecipient.confirmed_at.is_not(None))
        else:
            confirmation = confirmation.where(ContactNoticeRecipient.confirmed_at.is_(None))
        conditions.append(confirmation.exists())
    total = int(await db.scalar(select(func.count(ContactNotice.id)).where(*conditions)) or 0)
    statement = (
        select(ContactNotice)
        .where(*conditions)
        .order_by(ContactNotice.created_at.desc(), ContactNotice.id.desc())
    )
    statement = statement.offset((request.page - 1) * request.page_size).limit(request.page_size)
    return (await db.scalars(statement)).all(), total


# endregion


async def count_notice_recipients(db, notice):
    """执行close_if_due所需的数据库查询；权限由调用它的服务检查。"""
    return await db.scalar(
        select(func.count())
        .select_from(ContactNoticeRecipient)
        .join(Employee, Employee.id == ContactNoticeRecipient.employee_id)
        .where(
            ContactNoticeRecipient.notice_id == notice.id,
            Employee.is_active.is_(True),
            Employee.store_id == ContactNoticeRecipient.store_id,
        )
    )


async def count_unconfirmed_recipients(db, notice):
    """执行close_if_due所需的数据库查询；权限由调用它的服务检查。"""
    return await db.scalar(
        select(func.count())
        .select_from(ContactNoticeRecipient)
        .join(Employee, Employee.id == ContactNoticeRecipient.employee_id)
        .where(
            ContactNoticeRecipient.notice_id == notice.id,
            ContactNoticeRecipient.confirmed_at.is_(None),
            Employee.is_active.is_(True),
            Employee.store_id == ContactNoticeRecipient.store_id,
        )
    )


async def get_published_notices_for_update(db):
    """执行refresh_expired_notices所需的数据库查询；权限由调用它的服务检查。"""
    return await db.scalars(
        select(ContactNotice)
        .where(ContactNotice.status == "published", ContactNotice.deadline_at <= business_now())
        .order_by(ContactNotice.id)
        .with_for_update()
    )


async def get_notice_department(db, department_id):
    """执行resolve_recipients所需的数据库查询；权限由调用它的服务检查。"""
    store_query_2 = select(Department).where(Department.id == department_id)
    if db.info.get("read_store_id") is not None and (not db.info.get("company_catalog_read")):
        enabled_departments = select(StoreDepartment.department_id).where(
            StoreDepartment.store_id == db.info["read_store_id"],
            StoreDepartment.is_active.is_(True),
        )
        store_query_2 = store_query_2.where(Department.id.in_(enabled_departments))
    return await db.scalar(store_query_2)


async def get_target_employees(db, employee, headquarters, request, department_id):
    """构建并执行resolve_recipients_query的查询，店铺条件在这里明确添加。"""
    statement = select(Employee).where(Employee.is_active.is_(True))
    if (
        db.info.get("private_employee_path")
        and db.info.get("actor_role") != EmployeeRole.HEADQUARTERS
    ):
        statement = statement.where(Employee.store_id == db.info["own_store_id"])
    if headquarters:
        statement = statement.where(Employee.role != EmployeeRole.HEADQUARTERS)
        if request.store_ids:
            statement = statement.where(Employee.store_id.in_(request.store_ids))
    else:
        statement = statement.where(Employee.store_id == employee.store_id)
    if request.target_type == "department":
        statement = statement.where(Employee.department_id == department_id)
    elif request.target_type == "personal":
        statement = statement.where(Employee.id.in_(request.employee_ids))
    return await db.scalars(statement.order_by(Employee.id))


async def get_active_target_stores(db, request):
    """执行resolve_recipients所需的数据库查询；权限由调用它的服务检查。"""
    return await db.scalars(
        select(Store).where(Store.id.in_(request.store_ids), Store.is_active.is_(True))
    )


async def get_notice_publisher(db, notice):
    """执行build_response所需的数据库查询；权限由调用它的服务检查。"""
    return await db.get(Employee, notice.publisher_id)


async def get_publisher_department(db, notice):
    """执行build_response所需的数据库查询；权限由调用它的服务检查。"""
    store_query_3 = select(Department).where(Department.id == notice.department_id)
    if db.info.get("read_store_id") is not None and (not db.info.get("company_catalog_read")):
        enabled_departments = select(StoreDepartment.department_id).where(
            StoreDepartment.store_id == db.info["read_store_id"],
            StoreDepartment.is_active.is_(True),
        )
        store_query_3 = store_query_3.where(Department.id.in_(enabled_departments))
    return await db.scalar(store_query_3)


async def get_notice_recipient(db, employee, notice):
    """执行detail_notice所需的数据库查询；权限由调用它的服务检查。"""
    return await db.scalar(
        select(ContactNoticeRecipient).where(
            ContactNoticeRecipient.notice_id == notice.id,
            ContactNoticeRecipient.employee_id == employee.id,
        )
    )


async def get_notice_recipient_for_read(db, employee, notice):
    """执行detail_notice所需的数据库查询；权限由调用它的服务检查。"""
    return await db.scalar(
        select(ContactNoticeRecipient.id)
        .where(
            ContactNoticeRecipient.notice_id == notice.id,
            ContactNoticeRecipient.store_id == employee.store_id,
        )
        .limit(1)
    )


def add_notice(db, notice):
    """执行save_notice所需的数据库新增；权限由调用它的服务检查。"""
    return db.add(notice)


def add_draft_recipient(db, notice, recipient):
    """执行save_notice所需的数据库新增；权限由调用它的服务检查。"""
    return db.add(
        ContactNoticeRecipient(
            notice_id=notice.id, employee_id=recipient.id, store_id=recipient.store_id
        )
    )


async def delete_draft_recipients(db, notice):
    """执行save_notice所需的数据库查询或更新；权限由调用它的服务检查。"""
    return await db.execute(
        delete(ContactNoticeRecipient).where(ContactNoticeRecipient.notice_id == notice.id)
    )


async def get_notice_recipient_for_action(db, employee, notice):
    """执行action_notice所需的数据库查询；权限由调用它的服务检查。"""
    return await db.scalar(
        select(ContactNoticeRecipient).where(
            ContactNoticeRecipient.notice_id == notice.id,
            ContactNoticeRecipient.employee_id == employee.id,
        )
    )


async def delete_publish_recipients(db, notice):
    """执行action_notice所需的数据库查询或更新；权限由调用它的服务检查。"""
    return await db.execute(
        delete(ContactNoticeRecipient).where(ContactNoticeRecipient.notice_id == notice.id)
    )


def add_publish_recipient(db, notice, recipient):
    """执行action_notice所需的数据库新增；权限由调用它的服务检查。"""
    return db.add(
        ContactNoticeRecipient(
            notice_id=notice.id, employee_id=recipient.id, store_id=recipient.store_id
        )
    )


async def delete_notice_recipients(db, notice):
    """执行action_notice所需的数据库查询或更新；权限由调用它的服务检查。"""
    return await db.execute(
        delete(ContactNoticeRecipient).where(ContactNoticeRecipient.notice_id == notice.id)
    )


async def delete_notice(db, notice):
    """执行action_notice所需的数据库删除；权限由调用它的服务检查。"""
    return await db.delete(notice)


async def count_unread_notices(db, current_employee_id):
    """构建并执行get_summary_query的查询，店铺条件在这里明确添加。"""
    base = (
        select(func.count())
        .select_from(ContactNoticeRecipient)
        .join(ContactNotice)
        .where(
            ContactNoticeRecipient.employee_id == current_employee_id,
            ContactNoticeRecipient.store_id == db.info.get("own_store_id", 1),
            ContactNotice.status == "published",
            ContactNotice.starts_at <= business_now(),
        )
    )
    return await db.scalar(base.where(ContactNoticeRecipient.read_at.is_(None)))


async def count_pending_confirmations(db, current_employee_id):
    """执行get_summary_service所需的数据库查询；权限由调用它的服务检查。"""
    base = (
        select(func.count())
        .select_from(ContactNoticeRecipient)
        .join(ContactNotice)
        .where(
            ContactNoticeRecipient.employee_id == current_employee_id,
            ContactNoticeRecipient.store_id == db.info.get("own_store_id", 1),
            ContactNotice.status == "published",
            ContactNotice.starts_at <= business_now(),
        )
    )
    return await db.scalar(base.where(ContactNoticeRecipient.confirmed_at.is_(None)))


async def get_audience_employees(db, employee):
    """构建并执行get_audience_query的查询，店铺条件在这里明确添加。"""
    employees_query = (
        select(Employee)
        .where(Employee.is_active.is_(True))
        .order_by(Employee.department_id, Employee.id)
    )
    if (
        db.info.get("private_employee_path")
        and db.info.get("actor_role") != EmployeeRole.HEADQUARTERS
    ):
        employees_query = employees_query.where(Employee.store_id == db.info["own_store_id"])
    departments_query = select(Department).where(Department.is_active.is_(True))
    if db.info.get("read_store_id") is not None and (not db.info.get("company_catalog_read")):
        enabled_departments = select(StoreDepartment.department_id).where(
            StoreDepartment.store_id == db.info["read_store_id"],
            StoreDepartment.is_active.is_(True),
        )
        departments_query = departments_query.where(Department.id.in_(enabled_departments))
    if employee.role != EmployeeRole.HEADQUARTERS:
        employees_query = employees_query.where(Employee.store_id == employee.store_id)
    else:
        employees_query = employees_query.where(Employee.role != EmployeeRole.HEADQUARTERS)
    if employee.role not in (EmployeeRole.STORE_MANAGER, EmployeeRole.HEADQUARTERS):
        employees_query = employees_query.where(Employee.department_id == employee.department_id)
        departments_query = departments_query.where(Department.id == employee.department_id)
    return await db.scalars(employees_query)


async def get_audience_departments(db, employee):
    """执行get_audience_service所需的数据库查询；权限由调用它的服务检查。"""
    employees_query = (
        select(Employee)
        .where(Employee.is_active.is_(True))
        .order_by(Employee.department_id, Employee.id)
    )
    if (
        db.info.get("private_employee_path")
        and db.info.get("actor_role") != EmployeeRole.HEADQUARTERS
    ):
        employees_query = employees_query.where(Employee.store_id == db.info["own_store_id"])
    departments_query = select(Department).where(Department.is_active.is_(True))
    if db.info.get("read_store_id") is not None and (not db.info.get("company_catalog_read")):
        enabled_departments = select(StoreDepartment.department_id).where(
            StoreDepartment.store_id == db.info["read_store_id"],
            StoreDepartment.is_active.is_(True),
        )
        departments_query = departments_query.where(Department.id.in_(enabled_departments))
    if employee.role != EmployeeRole.HEADQUARTERS:
        employees_query = employees_query.where(Employee.store_id == employee.store_id)
    else:
        employees_query = employees_query.where(Employee.role != EmployeeRole.HEADQUARTERS)
    if employee.role not in (EmployeeRole.STORE_MANAGER, EmployeeRole.HEADQUARTERS):
        employees_query = employees_query.where(Employee.department_id == employee.department_id)
        departments_query = departments_query.where(Department.id == employee.department_id)
    return await db.scalars(departments_query)
