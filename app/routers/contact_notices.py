"""联络事项 API：账号验证、分页查询、发布与确认。"""

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.business_time import business_now
from app.dependencies.auth import get_verified_current_employee_id
from app.dependencies.db import get_db
from app.models.contact_notice import ContactNotice, ContactNoticeRecipient
from app.models.department import Department
from app.models.employee import Employee
from app.models.enums import EmployeeRole
from app.schemas.base import ResponseModel
from app.schemas.contact_notices_requests import (
    ContactNoticeActionRequest,
    ContactNoticeListRequest,
    ContactNoticeUpdateRequest,
    ContactNoticeWriteRequest,
)
from app.schemas.contact_notices_responses import (
    ContactNoticeDetailResponse,
    ContactNoticeListResponse,
    ContactNoticeSummaryResponse,
)
from app.services.contact_notices import (
    action_notice,
    current_employee,
    detail_notice,
    list_notices,
    refresh_expired_notices,
    save_notice,
)

contact_notices_router = APIRouter(prefix="/contact-notices", tags=["contact-notices"])


# region 分页查询和提醒
@contact_notices_router.get(
    "/list", response_model=ResponseModel[ContactNoticeListResponse], summary="获取联络事项列表"
)
async def get_list(
    request: ContactNoticeListRequest = Depends(),
    current_employee_id: int = Depends(get_verified_current_employee_id),
    db: AsyncSession = Depends(get_db),
):
    return ResponseModel(data=await list_notices(request, current_employee_id, db))


@contact_notices_router.get(
    "/summary",
    response_model=ResponseModel[ContactNoticeSummaryResponse],
    summary="获取未读和待确认数量",
)
async def get_summary(
    current_employee_id: int = Depends(get_verified_current_employee_id),
    db: AsyncSession = Depends(get_db),
):
    await refresh_expired_notices(db)
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
    unread = int(await db.scalar(base.where(ContactNoticeRecipient.read_at.is_(None))) or 0)
    pending = int(await db.scalar(base.where(ContactNoticeRecipient.confirmed_at.is_(None))) or 0)
    return ResponseModel(data=ContactNoticeSummaryResponse(unread=unread, pending=pending))


@contact_notices_router.get("/audience", summary="获取允许选择的部门和接收员工")
async def get_audience(
    current_employee_id: int = Depends(get_verified_current_employee_id),
    db: AsyncSession = Depends(get_db),
):
    employee = await current_employee(current_employee_id, db)
    if employee.role not in (EmployeeRole.STORE_MANAGER, EmployeeRole.HEADQUARTERS) and employee.department_id is None:
        return ResponseModel(data={"employees": [], "departments": []})
    employees_query = (
        select(Employee)
        .where(Employee.is_active.is_(True))
        .order_by(Employee.department_id, Employee.id)
    )
    departments_query = select(Department).where(Department.is_active.is_(True))
    if employee.role != EmployeeRole.HEADQUARTERS:
        employees_query = employees_query.where(Employee.store_id == employee.store_id)
    else:
        employees_query = employees_query.where(Employee.role != EmployeeRole.HEADQUARTERS)
    if employee.role not in (EmployeeRole.STORE_MANAGER, EmployeeRole.HEADQUARTERS):
        employees_query = employees_query.where(Employee.department_id == employee.department_id)
        departments_query = departments_query.where(Department.id == employee.department_id)
    employees = []
    for item in (await db.scalars(employees_query)).all():
        employees.append({"id": item.id, "name": item.name, "department_id": item.department_id, "store_id": item.store_id})
    departments = []
    for item in (await db.scalars(departments_query)).all():
        departments.append({"id": item.id, "name": item.name})
    return ResponseModel(data={"employees": employees, "departments": departments})


# endregion


# region 详情创建和修改
@contact_notices_router.get(
    "/{notice_id}",
    response_model=ResponseModel[ContactNoticeDetailResponse],
    summary="获取联络事项详情并记录查看",
)
async def get_detail(
    notice_id: int,
    current_employee_id: int = Depends(get_verified_current_employee_id),
    db: AsyncSession = Depends(get_db),
):
    return ResponseModel(data=await detail_notice(notice_id, current_employee_id, db))


@contact_notices_router.post(
    "", response_model=ResponseModel[ContactNoticeDetailResponse], summary="创建联络事项草稿"
)
async def create_notice(
    request: ContactNoticeWriteRequest,
    current_employee_id: int = Depends(get_verified_current_employee_id),
    db: AsyncSession = Depends(get_db),
):
    return ResponseModel(data=await save_notice(request, current_employee_id, db))


@contact_notices_router.put(
    "/{notice_id}",
    response_model=ResponseModel[ContactNoticeDetailResponse],
    summary="修改联络事项草稿",
)
async def update_notice(
    notice_id: int,
    request: ContactNoticeUpdateRequest,
    current_employee_id: int = Depends(get_verified_current_employee_id),
    db: AsyncSession = Depends(get_db),
):
    return ResponseModel(data=await save_notice(request, current_employee_id, db, notice_id))


# endregion


# region 发布关闭撤回和确认
@contact_notices_router.post(
    "/{notice_id}/publish",
    response_model=ResponseModel[ContactNoticeDetailResponse],
    summary="发布联络事项",
)
async def publish_notice(
    notice_id: int,
    request: ContactNoticeActionRequest,
    current_employee_id: int = Depends(get_verified_current_employee_id),
    db: AsyncSession = Depends(get_db),
):
    return ResponseModel(
        data=await action_notice(notice_id, "publish", request, current_employee_id, db)
    )


@contact_notices_router.post(
    "/{notice_id}/close",
    response_model=ResponseModel[ContactNoticeDetailResponse],
    summary="关闭联络事项并保留历史",
)
async def close_notice(
    notice_id: int,
    request: ContactNoticeActionRequest,
    current_employee_id: int = Depends(get_verified_current_employee_id),
    db: AsyncSession = Depends(get_db),
):
    return ResponseModel(
        data=await action_notice(notice_id, "close", request, current_employee_id, db)
    )


@contact_notices_router.post(
    "/{notice_id}/withdraw",
    response_model=ResponseModel[ContactNoticeDetailResponse],
    summary="撤回联络事项",
)
async def withdraw_notice(
    notice_id: int,
    request: ContactNoticeActionRequest,
    current_employee_id: int = Depends(get_verified_current_employee_id),
    db: AsyncSession = Depends(get_db),
):
    return ResponseModel(
        data=await action_notice(notice_id, "withdraw", request, current_employee_id, db)
    )


@contact_notices_router.post(
    "/{notice_id}/confirm",
    response_model=ResponseModel[ContactNoticeDetailResponse],
    summary="确认联络事项，允许逾期补确认",
)
async def confirm_notice(
    notice_id: int,
    current_employee_id: int = Depends(get_verified_current_employee_id),
    db: AsyncSession = Depends(get_db),
):
    return ResponseModel(
        data=await action_notice(notice_id, "confirm", None, current_employee_id, db)
    )


@contact_notices_router.delete("/{notice_id}", summary="删除联络事项草稿")
async def delete_notice(
    notice_id: int,
    request: ContactNoticeActionRequest,
    current_employee_id: int = Depends(get_verified_current_employee_id),
    db: AsyncSession = Depends(get_db),
):
    await action_notice(notice_id, "delete", request, current_employee_id, db)
    return ResponseModel(data={"deleted": True})


# endregion
