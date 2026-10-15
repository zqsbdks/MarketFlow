"""联络事项 API：账号验证、分页查询、发布与确认。"""

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies.auth import get_verified_current_employee_id
from app.dependencies.db import get_db
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
    detail_notice,
    get_audience_service,
    get_summary_service,
    list_notices,
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
    *,
    http_request: Request,
):
    return ResponseModel(
        data=await list_notices(request, current_employee_id, db, http_request=http_request)
    )


@contact_notices_router.get(
    "/summary",
    response_model=ResponseModel[ContactNoticeSummaryResponse],
    summary="获取未读和待确认数量",
)
async def get_summary(
    current_employee_id: int = Depends(get_verified_current_employee_id),
    db: AsyncSession = Depends(get_db),
    *,
    http_request: Request,
):
    return await get_summary_service(
        current_employee_id=current_employee_id, db=db, http_request=http_request
    )


@contact_notices_router.get("/audience", summary="获取允许选择的部门和接收员工")
async def get_audience(
    current_employee_id: int = Depends(get_verified_current_employee_id),
    db: AsyncSession = Depends(get_db),
    *,
    http_request: Request,
):
    return await get_audience_service(
        current_employee_id=current_employee_id, db=db, http_request=http_request
    )


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
    *,
    http_request: Request,
):
    return ResponseModel(
        data=await detail_notice(notice_id, current_employee_id, db, http_request=http_request)
    )


@contact_notices_router.post(
    "", response_model=ResponseModel[ContactNoticeDetailResponse], summary="创建联络事项草稿"
)
async def create_notice(
    request: ContactNoticeWriteRequest,
    current_employee_id: int = Depends(get_verified_current_employee_id),
    db: AsyncSession = Depends(get_db),
    *,
    http_request: Request,
):
    return ResponseModel(
        data=await save_notice(request, current_employee_id, db, http_request=http_request)
    )


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
    *,
    http_request: Request,
):
    return ResponseModel(
        data=await save_notice(
            request, current_employee_id, db, notice_id, http_request=http_request
        )
    )


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
    *,
    http_request: Request,
):
    return ResponseModel(
        data=await action_notice(
            notice_id, "publish", request, current_employee_id, db, http_request=http_request
        )
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
    *,
    http_request: Request,
):
    return ResponseModel(
        data=await action_notice(
            notice_id, "close", request, current_employee_id, db, http_request=http_request
        )
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
    *,
    http_request: Request,
):
    return ResponseModel(
        data=await action_notice(
            notice_id, "withdraw", request, current_employee_id, db, http_request=http_request
        )
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
    *,
    http_request: Request,
):
    return ResponseModel(
        data=await action_notice(
            notice_id, "confirm", None, current_employee_id, db, http_request=http_request
        )
    )


@contact_notices_router.delete("/{notice_id}", summary="删除联络事项草稿")
async def delete_notice(
    notice_id: int,
    request: ContactNoticeActionRequest,
    current_employee_id: int = Depends(get_verified_current_employee_id),
    db: AsyncSession = Depends(get_db),
    *,
    http_request: Request,
):
    await action_notice(
        notice_id, "delete", request, current_employee_id, db, http_request=http_request
    )
    return ResponseModel(data={"deleted": True})


# endregion
