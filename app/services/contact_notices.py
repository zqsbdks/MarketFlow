"""联络事项权限、发布、确认及自动关闭业务。"""

from fastapi import HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.business_time import business_now as _business_now
from app.crud import contact_notices as data_access
from app.crud.auth import get_employee_by_id
from app.crud.contact_notices import get_notice, get_notices, get_recipients
from app.crud.operation_audit_logs import create_operation_audit_log
from app.crud.stores import first_active_store_id, get_store_by_id
from app.models.contact_notice import ContactNotice
from app.models.enums import EmployeeRole
from app.schemas.base import ResponseModel
from app.schemas.contact_notices_responses import (
    ContactNoticeDetailResponse,
    ContactNoticeListResponse,
    ContactNoticeSummaryResponse,
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
        total = int(await data_access.count_notice_recipients(db=db, notice=notice) or 0)
        pending = int(await data_access.count_unconfirmed_recipients(db=db, notice=notice) or 0)
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
    notices = (await data_access.get_published_notices_for_update(db=db)).all()
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
        selected_stores = (await data_access.get_active_target_stores(db=db, request=request)).all()
        if len(selected_stores) != len(set(request.store_ids)):
            raise HTTPException(400, "目标门店不存在或已停用")
    manager = employee.role in (EmployeeRole.STORE_MANAGER, EmployeeRole.HEADQUARTERS)
    if request.target_type == "all" and not manager:
        raise HTTPException(403, "只有店长可以向全体员工发布")
    if not manager and employee.department_id is None:
        raise HTTPException(403, "请先配置所属部门")
    department_id = None
    if request.target_type == "department":
        if manager:
            department_id = request.department_id
        else:
            department_id = employee.department_id
        if not manager and request.department_id not in (None, employee.department_id):
            raise HTTPException(403, "只能向自己部门发布")
        if department_id:
            department = await data_access.get_notice_department(db=db, department_id=department_id)
        else:
            department = None
        if department is None or not department.is_active:
            raise HTTPException(400, "请选择启用的部门")
    elif request.target_type == "personal":
        if not request.employee_ids or any(value <= 0 for value in request.employee_ids):
            raise HTTPException(400, "请选择接收员工")
    employees = (
        await data_access.get_target_employees(
            db=db,
            employee=employee,
            headquarters=headquarters,
            request=request,
            department_id=department_id,
        )
    ).all()
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
        rows_values = []
        for rows_row in rows:
            if rows_row[0].store_id == employee.store_id:
                rows_values.append(rows_row)
        rows = rows_values
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
    publisher = await data_access.get_notice_publisher(db=db, notice=notice)
    if notice.department_id:
        department = await data_access.get_publisher_department(db=db, notice=notice)
    else:
        department = None
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
    if department:
        department_name_value = department.name
    else:
        department_name_value = None
    if mine:
        read_at_value = mine.read_at
    else:
        read_at_value = None
    if mine:
        confirmed_at_value = mine.confirmed_at
    else:
        confirmed_at_value = None
    data.update(
        source=notice.source or "store",
        store_id=notice.store_id,
        target_store_ids=notice.target_store_ids or [],
        can_view_recipients=view_recipients,
        publisher_name=publisher.name,
        department_name=department_name_value,
        read_at=read_at_value,
        confirmed_at=confirmed_at_value,
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
        if view_recipients:
            data["recipients"] = recipients
        else:
            data["recipients"] = []
        if can_manage(notice, employee):
            result_values = []
            for result_row in rows:
                result_values.append(result_row[0].employee_id)
            data["employee_ids"] = result_values
        else:
            data["employee_ids"] = []
        return ContactNoticeDetailResponse(**data)
    return data


async def list_notices(request, employee_id, db, *, http_request: Request | None = None):
    """按收到、自己发布、店长管理三个视角查询分页结果。"""

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
        if not is_headquarters:
            selected_store_id = access_employee.store_id
        # 这里只记录本次查询参数；CRUD 会明确读取并添加 store_id 条件。
        db.info.update(
            actor_id=access_employee.id,
            actor_role=access_employee.role,
            own_store_id=access_employee.store_id,
            read_store_id=selected_store_id,
            write_store_id=access_employee.store_id,
            company_management=False,
            company_catalog_read=is_headquarters,
            private_employee_path=False,
            store_context=True,
        )
        http_request.state.store_id = selected_store_id
        http_request.state.employee_id = access_employee.id
        http_request.state.own_store_id = access_employee.store_id

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


async def detail_notice(notice_id, employee_id, db, *, http_request: Request | None = None):
    """验证可见范围，记录第一次查看，并返回事项及允许查看的名单。"""
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
        if not is_headquarters:
            selected_store_id = access_employee.store_id
        db.info.update(
            actor_id=access_employee.id,
            actor_role=access_employee.role,
            own_store_id=access_employee.store_id,
            read_store_id=selected_store_id,
            write_store_id=access_employee.store_id,
            company_management=False,
            company_catalog_read=is_headquarters,
            private_employee_path=False,
            store_context=True,
        )
        http_request.state.store_id = selected_store_id
        http_request.state.employee_id = access_employee.id
        http_request.state.own_store_id = access_employee.store_id
    employee = await current_employee(employee_id, db)
    notice = await get_notice(notice_id, db, lock=True)
    if notice is None:
        raise HTTPException(404, "联络事项不存在")
    mine = await data_access.get_notice_recipient(db=db, employee=employee, notice=notice)
    manager_hq_view = (
        employee.role == EmployeeRole.STORE_MANAGER
        and notice.source == "headquarters"
        and bool(
            await data_access.get_notice_recipient_for_read(db=db, employee=employee, notice=notice)
        )
    )
    if (
        not can_manage(notice, employee)
        and (not manager_hq_view)
        and (
            mine is None
            or mine.store_id != employee.store_id
            or notice.status not in ("published", "closed")
            or (notice.starts_at > business_now())
        )
    ):
        raise HTTPException(403, "无权查看此事项")
    await close_if_due(notice, db)
    if (
        mine
        and mine.read_at is None
        and (notice.status in ("published", "closed"))
        and (notice.starts_at <= business_now())
    ):
        mine.read_at = business_now()
        await audit(notice, "read", employee.id, db)
    await db.commit()
    await db.refresh(notice)
    return await build_response(notice, employee, db, detail=True)


# endregion


# region 创建修改和状态操作
async def save_notice(
    request, employee_id, db, notice_id=None, *, http_request: Request | None = None
):
    """创建或修改草稿，撤回后修改会清空旧确认并回到草稿状态。"""
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
        if not is_headquarters:
            selected_store_id = access_employee.store_id
        db.info.update(
            actor_id=access_employee.id,
            actor_role=access_employee.role,
            own_store_id=access_employee.store_id,
            read_store_id=selected_store_id,
            write_store_id=access_employee.store_id,
            company_management=False,
            company_catalog_read=is_headquarters,
            private_employee_path=False,
            store_context=True,
        )
        http_request.state.store_id = selected_store_id
        http_request.state.employee_id = access_employee.id
        http_request.state.own_store_id = access_employee.store_id
    employee = await current_employee(employee_id, db)
    recipients, department_id, starts_at = await resolve_recipients(request, employee, db)
    before = None
    if notice_id is None:
        if employee.role == EmployeeRole.HEADQUARTERS:
            source_value = "headquarters"
        else:
            source_value = "store"
        notice = ContactNotice(
            publisher_id=employee.id,
            status="draft",
            version=1,
            store_id=employee.store_id,
            source=source_value,
        )
        data_access.add_notice(db=db, notice=notice)
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
        await data_access.delete_draft_recipients(db=db, notice=notice)
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
    if notice.source == "headquarters":
        notice.target_store_ids = request.store_ids
    else:
        notice.target_store_ids = []
    await db.flush()
    for recipient in recipients:
        data_access.add_draft_recipient(db=db, notice=notice, recipient=recipient)
    if notice_id is None:
        selected_value = "create"
    else:
        selected_value = "update"
    await audit(notice, selected_value, employee.id, db, request.reason, before)
    await db.commit()
    await db.refresh(notice)
    return await build_response(notice, employee, db, detail=True)


async def action_notice(
    notice_id, action, request, employee_id, db, *, http_request: Request | None = None
):
    """锁住主表后发布、关闭、撤回或确认，确保并发确认只关闭一次。"""
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
        if not is_headquarters:
            selected_store_id = access_employee.store_id
        db.info.update(
            actor_id=access_employee.id,
            actor_role=access_employee.role,
            own_store_id=access_employee.store_id,
            read_store_id=selected_store_id,
            write_store_id=access_employee.store_id,
            company_management=False,
            company_catalog_read=is_headquarters,
            private_employee_path=False,
            store_context=True,
        )
        http_request.state.store_id = selected_store_id
        http_request.state.employee_id = access_employee.id
        http_request.state.own_store_id = access_employee.store_id
    employee = await current_employee(employee_id, db)
    notice = await get_notice(notice_id, db, lock=True)
    if notice is None:
        raise HTTPException(404, "联络事项不存在")
    if action == "confirm":
        record = await data_access.get_notice_recipient_for_action(
            db=db, employee=employee, notice=notice
        )
        if (
            record is None
            or record.store_id != employee.store_id
            or notice.status not in ("published", "closed")
            or (notice.starts_at > business_now())
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
            await data_access.delete_publish_recipients(db=db, notice=notice)
            for recipient in recipients:
                data_access.add_publish_recipient(db=db, notice=notice, recipient=recipient)
            notice.status = "published"
            notice.closed_at = None
            notice.close_reason = None
        elif action in ("close", "withdraw"):
            if notice.status not in ("published", "closed"):
                raise HTTPException(400, "此状态不能关闭或撤回")
            if action == "close":
                notice.status = "closed"
            else:
                notice.status = "withdrawn"
            notice.closed_at = business_now()
            if action == "close":
                notice.close_reason = "manual"
            else:
                notice.close_reason = "withdrawn"
        elif action == "delete":
            if notice.status != "draft":
                raise HTTPException(400, "只能删除草稿")
            await audit(notice, "delete", employee.id, db, request.reason, before)
            await data_access.delete_notice_recipients(db=db, notice=notice)
            await data_access.delete_notice(db=db, notice=notice)
            await db.commit()
            return None
        notice.version += 1
        await audit(notice, action, employee.id, db, request.reason, before)
    await db.commit()
    await db.refresh(notice)
    return await build_response(notice, employee, db, detail=True)


# endregion


async def get_summary_service(
    current_employee_id: int, db: AsyncSession, *, http_request: Request | None = None
):
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
        if not is_headquarters:
            selected_store_id = access_employee.store_id
        db.info.update(
            actor_id=access_employee.id,
            actor_role=access_employee.role,
            own_store_id=access_employee.store_id,
            read_store_id=selected_store_id,
            write_store_id=access_employee.store_id,
            company_management=False,
            company_catalog_read=is_headquarters,
            private_employee_path=False,
            store_context=True,
        )
        http_request.state.store_id = selected_store_id
        http_request.state.employee_id = access_employee.id
        http_request.state.own_store_id = access_employee.store_id
    await refresh_expired_notices(db)
    unread = int(
        await data_access.count_unread_notices(db=db, current_employee_id=current_employee_id) or 0
    )
    pending = int(
        await data_access.count_pending_confirmations(
            db=db, current_employee_id=current_employee_id
        )
        or 0
    )
    return ResponseModel(data=ContactNoticeSummaryResponse(unread=unread, pending=pending))


async def get_audience_service(
    current_employee_id: int, db: AsyncSession, *, http_request: Request | None = None
):
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
        if not is_headquarters:
            selected_store_id = access_employee.store_id
        db.info.update(
            actor_id=access_employee.id,
            actor_role=access_employee.role,
            own_store_id=access_employee.store_id,
            read_store_id=selected_store_id,
            write_store_id=access_employee.store_id,
            company_management=False,
            company_catalog_read=is_headquarters,
            private_employee_path=False,
            store_context=True,
        )
        http_request.state.store_id = selected_store_id
        http_request.state.employee_id = access_employee.id
        http_request.state.own_store_id = access_employee.store_id
    employee = await current_employee(current_employee_id, db)
    if (
        employee.role not in (EmployeeRole.STORE_MANAGER, EmployeeRole.HEADQUARTERS)
        and employee.department_id is None
    ):
        return ResponseModel(data={"employees": [], "departments": []})
    employees = []
    for item in (await data_access.get_audience_employees(db=db, employee=employee)).all():
        employees.append(
            {
                "id": item.id,
                "name": item.name,
                "department_id": item.department_id,
                "store_id": item.store_id,
            }
        )
    departments = []
    for department in (await data_access.get_audience_departments(db=db, employee=employee)).all():
        departments.append({"id": department.id, "name": department.name})
    return ResponseModel(data={"employees": employees, "departments": departments})
