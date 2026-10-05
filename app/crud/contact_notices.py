"""联络事项查询与行锁；接收范围使用发布时保存的员工名单。"""

from sqlalchemy import exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.contact_notice import ContactNotice, ContactNoticeRecipient
from app.models.department import Department
from app.models.employee import Employee
from app.models.enums import EmployeeRole


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
