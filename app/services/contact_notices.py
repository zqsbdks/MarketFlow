"""联络事项权限、发布、确认及自动关闭业务。"""

from fastapi import HTTPException
from sqlalchemy import delete, func, select

from app.core.business_time import business_now as _business_now
from app.crud.auth import get_employee_by_id
from app.crud.contact_notices import get_notice, get_notices, get_recipients
from app.crud.operation_audit_logs import create_operation_audit_log
from app.models.contact_notice import ContactNotice, ContactNoticeRecipient
from app.models.department import Department
from app.models.employee import Employee
from app.models.enums import EmployeeRole
from app.models.store import Store
from app.schemas.contact_notices_responses import (
    ContactNoticeDetailResponse,
    ContactNoticeListResponse,
    NoticeRecipientResponse,
)


def business_now():
    """MySQL DATETIME 按秒保存，响应与重复确认保持相同时间精度。"""
    return _business_now().replace(microsecond=0)


# region 账号和管理权限
async def current_employee(employee_id, db):
    """读取账号最新状态，正式员工和契约工拥有相同的部门发布权限。"""
    employee = await get_employee_by_id(employee_id=employee_id, db=db)
    if employee is None:
        raise HTTPException(401, "当前登录员工不存在", headers={"WWW-Authenticate": "Bearer"})
    if not employee.is_active:
        raise HTTPException(403, "账号已停用")
    if employee.must_change_password:
        raise HTTPException(403, "请先修改初始密码")
    return employee


def can_manage(notice, employee):
    """店长可管理所有事项，其他员工只能管理自己发布的事项。"""
    if employee.role == EmployeeRole.HEADQUARTERS:
        return notice.source == "headquarters"
    return notice.store_id == employee.store_id and (
        employee.role == EmployeeRole.STORE_MANAGER or notice.publisher_id == employee.id
    )


def check_version(notice, version):
    """前端版本与数据库版本不一致时，阻止覆盖他人的修改。"""
    if notice.version != version:
        raise HTTPException(409, "事项已被修改，请刷新后重试")


async def audit(notice, action, employee_id, db, reason=None, before=None):
    """审计与事项变更在同一事务提交，自动关闭使用空员工ID。"""
    await create_operation_audit_log(
        employee_id=employee_id,
        module="contact_notices",
        action=action,
        target_type="contact_notice",
        target_id=notice.id,
        before_data=before,
        after_data={
            "title": notice.title,
            "content": notice.content,
            "status": notice.status,
            "target_type": notice.target_type,
            "department_id": notice.department_id,
            "deadline_at": notice.deadline_at,
            "close_reason": notice.close_reason,
            "version": notice.version,
        },
        reason=reason,
        store_id=notice.store_id,
        db=db,
    )


# endregion


# region 自动关闭
async def close_if_due(notice, db):
    """调用者先锁住主表；截止关闭优先于全员确认关闭。"""
    if notice.status != "published":
        return
    now = business_now()
    reason = None
    if notice.deadline_at is not None and notice.deadline_at <= now:
        reason = "deadline"
    elif notice.close_on_all_confirmed:
        total = int(
            await db.scalar(
                select(func.count())
                .select_from(ContactNoticeRecipient)
                .join(Employee, Employee.id == ContactNoticeRecipient.employee_id)
                .where(
                    ContactNoticeRecipient.notice_id == notice.id,
                    Employee.is_active.is_(True),
                    Employee.store_id == ContactNoticeRecipient.store_id,
                )
            )
            or 0
        )
        pending = int(
            await db.scalar(
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
            or 0
        )
        if total > 0 and pending == 0:
            reason = "all_confirmed"
    if reason:
        notice.status = "closed"
        notice.closed_at = now
        notice.close_reason = reason
        notice.version += 1
        await audit(notice, "auto_close", None, db)


async def refresh_expired_notices(db):
    """启动和定时任务处理到期事项；行锁确保多实例不会重复关闭。"""
    notices = (
        await db.scalars(
            select(ContactNotice)
            .where(ContactNotice.status == "published", ContactNotice.deadline_at <= business_now())
            .order_by(ContactNotice.id)
            .with_for_update()
        )
    ).all()
    for notice in notices:
        await close_if_due(notice, db)
    await db.commit()


# endregion


# region 校验接收范围
async def resolve_recipients(request, employee, db):
    """校验目标范围并取得启用员工，个人范围逐一检查所属部门。"""
    headquarters = employee.role == EmployeeRole.HEADQUARTERS
    if request.store_ids and not headquarters:
        raise HTTPException(403, "只有总部可以指定目标门店")
    if headquarters and request.store_ids:
        selected_stores = (
            await db.scalars(
                select(Store).where(Store.id.in_(request.store_ids), Store.is_active.is_(True))
            )
        ).all()
        if len(selected_stores) != len(set(request.store_ids)):
            raise HTTPException(400, "目标门店不存在或已停用")
    manager = employee.role in (EmployeeRole.STORE_MANAGER, EmployeeRole.HEADQUARTERS)
    if request.target_type == "all" and not manager:
        raise HTTPException(403, "只有店长可以向全体员工发布")
    if not manager and employee.department_id is None:
        raise HTTPException(403, "请先配置所属部门")
    statement = select(Employee).where(Employee.is_active.is_(True))
    if headquarters:
        statement = statement.where(Employee.role != EmployeeRole.HEADQUARTERS)
        if request.store_ids:
            statement = statement.where(Employee.store_id.in_(request.store_ids))
    else:
        statement = statement.where(Employee.store_id == employee.store_id)
    department_id = None
    if request.target_type == "department":
        department_id = request.department_id if manager else employee.department_id
        if not manager and request.department_id not in (None, employee.department_id):
            raise HTTPException(403, "只能向自己部门发布")
        department = await db.get(Department, department_id) if department_id else None
        if department is None or not department.is_active:
            raise HTTPException(400, "请选择启用的部门")
        statement = statement.where(Employee.department_id == department_id)
    elif request.target_type == "personal":
        if not request.employee_ids or any(value <= 0 for value in request.employee_ids):
            raise HTTPException(400, "请选择接收员工")
        statement = statement.where(Employee.id.in_(request.employee_ids))
    employees = (await db.scalars(statement.order_by(Employee.id))).all()
    if not employees:
        raise HTTPException(400, "接收范围内没有启用的员工")
    if request.target_type == "personal":
        if len(employees) != len(set(request.employee_ids)):
            raise HTTPException(400, "接收员工不存在或已停用")
        if not headquarters:
            for recipient in employees:
                if recipient.store_id != employee.store_id:
                    raise HTTPException(403, "不能指定其他门店员工")
        if not manager:
            for recipient in employees:
                if recipient.department_id != employee.department_id:
                    raise HTTPException(403, "只能指定自己部门的员工")
            department_id = employee.department_id
    starts_at = request.starts_at or business_now()
    if starts_at.tzinfo is not None or (
        request.deadline_at and request.deadline_at.tzinfo is not None
    ):
        raise HTTPException(400, "请使用门店本地时间")
    if request.deadline_at and (
        request.deadline_at <= starts_at or request.deadline_at <= business_now()
    ):
        raise HTTPException(400, "截止时间必须晚于开始时间和当前时间")
    return employees, department_id, starts_at


# endregion


# region 组装列表和详情
async def build_response(notice, employee, db, *, detail=False):
    """组装确认统计；只有发布者和店长得到完整接收员工名单。"""
    rows = await get_recipients(notice.id, db)
    view_recipients = can_manage(notice, employee) or (
        employee.role == EmployeeRole.STORE_MANAGER and notice.source == "headquarters"
    )
    if employee.role == EmployeeRole.STORE_MANAGER and notice.source == "headquarters":
        rows = [row for row in rows if row[0].store_id == employee.store_id]
    mine = None
    confirmed_count = 0
    recipients = []
    for record, name, department_name in rows:
        if record.employee_id == employee.id:
            mine = record
        if record.confirmed_at is not None:
            confirmed_count += 1
        light = "yellow"
        if record.confirmed_at is not None:
            light = "green"
        elif notice.deadline_at and notice.deadline_at <= business_now():
            light = "red"
        recipients.append(
            NoticeRecipientResponse(
                store_id=record.store_id,
                employee_id=record.employee_id,
                name=name,
                department_name=department_name,
                read_at=record.read_at,
                confirmed_at=record.confirmed_at,
                light=light,
            )
        )
    publisher = await db.get(Employee, notice.publisher_id)
    department = await db.get(Department, notice.department_id) if notice.department_id else None
    data = {}
    for field in (
        "id",
        "title",
        "content",
        "priority",
        "target_type",
        "department_id",
        "publisher_id",
        "starts_at",
        "deadline_at",
        "close_on_all_confirmed",
        "status",
        "closed_at",
        "close_reason",
        "version",
        "created_at",
        "updated_at",
    ):
        data[field] = getattr(notice, field)
    data.update(
        source=notice.source or "store",
        store_id=notice.store_id,
        target_store_ids=notice.target_store_ids or [],
        can_view_recipients=view_recipients,
        publisher_name=publisher.name,
        department_name=department.name if department else None,
        read_at=mine.read_at if mine else None,
        confirmed_at=mine.confirmed_at if mine else None,
        recipient_count=len(rows),
        confirmed_count=confirmed_count,
        can_manage=can_manage(notice, employee),
        can_confirm=mine is not None
        and mine.store_id == employee.store_id
        and mine.confirmed_at is None
        and notice.status in ("published", "closed")
        and notice.starts_at <= business_now(),
    )
    if detail:
        data["recipients"] = recipients if view_recipients else []
        data["employee_ids"] = (
            [row[0].employee_id for row in rows] if can_manage(notice, employee) else []
        )
        return ContactNoticeDetailResponse(**data)
    return data


async def list_notices(request, employee_id, db):
    """按收到、自己发布、店长管理三个视角查询分页结果。"""
    employee = await current_employee(employee_id, db)
    if request.start_time and request.end_time and request.start_time > request.end_time:
        raise HTTPException(400, "开始时间不能晚于结束时间")
    for value in (request.start_time, request.end_time):
        if value and value.tzinfo is not None:
            raise HTTPException(400, "请使用门店本地时间")
    if request.view == "management" and employee.role not in (
        EmployeeRole.STORE_MANAGER,
        EmployeeRole.HEADQUARTERS,
    ):
        raise HTTPException(403, "只有店长可以查看全部事项")
    await refresh_expired_notices(db)
    notices, total = await get_notices(request, employee, business_now(), db)
    items = []
    for notice in notices:
        items.append(await build_response(notice, employee, db))
    return ContactNoticeListResponse(
        items=items,
        page=request.page,
        page_size=request.page_size,
        total=total,
        total_pages=(total + request.page_size - 1) // request.page_size,
    )


async def detail_notice(notice_id, employee_id, db):
    """验证可见范围，记录第一次查看，并返回事项及允许查看的名单。"""
    employee = await current_employee(employee_id, db)
    notice = await get_notice(notice_id, db, lock=True)
    if notice is None:
        raise HTTPException(404, "联络事项不存在")
    mine = await db.scalar(
        select(ContactNoticeRecipient).where(
            ContactNoticeRecipient.notice_id == notice.id,
            ContactNoticeRecipient.employee_id == employee.id,
        )
    )
    manager_hq_view = (
        employee.role == EmployeeRole.STORE_MANAGER
        and notice.source == "headquarters"
        and bool(
            await db.scalar(
                select(ContactNoticeRecipient.id)
                .where(
                    ContactNoticeRecipient.notice_id == notice.id,
                    ContactNoticeRecipient.store_id == employee.store_id,
                )
                .limit(1)
            )
        )
    )
    if (
        not can_manage(notice, employee)
        and not manager_hq_view
        and (
            mine is None
            or mine.store_id != employee.store_id
            or notice.status not in ("published", "closed")
            or notice.starts_at > business_now()
        )
    ):
        raise HTTPException(403, "无权查看此事项")
    await close_if_due(notice, db)
    # 已读时间仅用于记录，前端仍只显示确认灯号。
    if (
        mine
        and mine.read_at is None
        and notice.status in ("published", "closed")
        and notice.starts_at <= business_now()
    ):
        mine.read_at = business_now()
        await audit(notice, "read", employee.id, db)
    await db.commit()
    await db.refresh(notice)
    return await build_response(notice, employee, db, detail=True)


# endregion


# region 创建修改和状态操作
async def save_notice(request, employee_id, db, notice_id=None):
    """创建或修改草稿，撤回后修改会清空旧确认并回到草稿状态。"""
    employee = await current_employee(employee_id, db)
    recipients, department_id, starts_at = await resolve_recipients(request, employee, db)
    before = None
    if notice_id is None:
        notice = ContactNotice(
            publisher_id=employee.id,
            status="draft",
            version=1,
            store_id=employee.store_id,
            source="headquarters" if employee.role == EmployeeRole.HEADQUARTERS else "store",
        )
        db.add(notice)
    else:
        notice = await get_notice(notice_id, db, lock=True)
        if notice is None:
            raise HTTPException(404, "联络事项不存在")
        if not can_manage(notice, employee):
            raise HTTPException(403, "无权修改此事项")
        check_version(notice, request.expected_version)
        if notice.status not in ("draft", "withdrawn"):
            raise HTTPException(400, "已发布事项请撤回后重新发布，避免已确认员工错过修改")
        before = {"title": notice.title, "content": notice.content, "version": notice.version}
        notice.version += 1
        notice.status = "draft"
        notice.closed_at = None
        notice.close_reason = None
        await db.execute(
            delete(ContactNoticeRecipient).where(ContactNoticeRecipient.notice_id == notice.id)
        )
    for field in (
        "title",
        "content",
        "priority",
        "target_type",
        "deadline_at",
        "close_on_all_confirmed",
    ):
        setattr(notice, field, getattr(request, field))
    notice.department_id = department_id
    notice.starts_at = starts_at
    notice.target_store_ids = request.store_ids if notice.source == "headquarters" else []
    await db.flush()
    for recipient in recipients:
        db.add(
            ContactNoticeRecipient(
                notice_id=notice.id, employee_id=recipient.id, store_id=recipient.store_id
            )
        )
    await audit(
        notice, "create" if notice_id is None else "update", employee.id, db, request.reason, before
    )
    await db.commit()
    await db.refresh(notice)
    return await build_response(notice, employee, db, detail=True)


async def action_notice(notice_id, action, request, employee_id, db):
    """锁住主表后发布、关闭、撤回或确认，确保并发确认只关闭一次。"""
    employee = await current_employee(employee_id, db)
    notice = await get_notice(notice_id, db, lock=True)
    if notice is None:
        raise HTTPException(404, "联络事项不存在")
    if action == "confirm":
        record = await db.scalar(
            select(ContactNoticeRecipient).where(
                ContactNoticeRecipient.notice_id == notice.id,
                ContactNoticeRecipient.employee_id == employee.id,
            )
        )
        if (
            record is None
            or record.store_id != employee.store_id
            or notice.status not in ("published", "closed")
            or notice.starts_at > business_now()
        ):
            raise HTTPException(403, "此事项不能确认")
        if record.confirmed_at is None:
            record.confirmed_at = business_now()
            record.read_at = record.read_at or record.confirmed_at
            await audit(notice, "confirm", employee.id, db)
        await db.flush()
        await close_if_due(notice, db)
    else:
        if not can_manage(notice, employee):
            raise HTTPException(403, "无权管理此事项")
        check_version(notice, request.expected_version)
        before = {"status": notice.status, "version": notice.version}
        if action == "publish":
            if notice.status not in ("draft", "withdrawn"):
                raise HTTPException(400, "此状态不能发布")
            if notice.deadline_at and notice.deadline_at <= business_now():
                raise HTTPException(400, "截止时间已过，请创建新的事项")
            # 发布时重新生成当前有效员工名单；避免草稿阶段员工调动造成范围错误。
            from app.schemas.contact_notices_requests import ContactNoticeWriteRequest

            rows = await get_recipients(notice.id, db)
            ids = []
            for row in rows:
                ids.append(row[0].employee_id)
            settings = ContactNoticeWriteRequest(
                store_ids=notice.target_store_ids or [],
                title=notice.title,
                content=notice.content,
                target_type=notice.target_type,
                department_id=notice.department_id,
                employee_ids=ids,
                starts_at=notice.starts_at,
                deadline_at=notice.deadline_at,
            )
            recipients, _, _ = await resolve_recipients(settings, employee, db)
            await db.execute(
                delete(ContactNoticeRecipient).where(ContactNoticeRecipient.notice_id == notice.id)
            )
            for recipient in recipients:
                db.add(
                    ContactNoticeRecipient(
                        notice_id=notice.id, employee_id=recipient.id, store_id=recipient.store_id
                    )
                )
            notice.status = "published"
            notice.closed_at = None
            notice.close_reason = None
        elif action in ("close", "withdraw"):
            if notice.status not in ("published", "closed"):
                raise HTTPException(400, "此状态不能关闭或撤回")
            notice.status = "closed" if action == "close" else "withdrawn"
            notice.closed_at = business_now()
            notice.close_reason = "manual" if action == "close" else "withdrawn"
        elif action == "delete":
            if notice.status != "draft":
                raise HTTPException(400, "只能删除草稿")
            await audit(notice, "delete", employee.id, db, request.reason, before)
            await db.execute(
                delete(ContactNoticeRecipient).where(ContactNoticeRecipient.notice_id == notice.id)
            )
            await db.delete(notice)
            await db.commit()
            return None
        notice.version += 1
        await audit(notice, action, employee.id, db, request.reason, before)
    await db.commit()
    await db.refresh(notice)
    return await build_response(notice, employee, db, detail=True)


# endregion
