"""联络事项列表、详情和确认名单响应。"""

from datetime import datetime

from pydantic import BaseModel


# region 事项和接收员工
class NoticeRecipientResponse(BaseModel):
    store_id: int | None = None
    employee_id: int
    name: str
    department_name: str | None
    read_at: datetime | None
    confirmed_at: datetime | None
    light: str


class ContactNoticeItemResponse(BaseModel):
    source: str = "store"
    store_id: int | None = None
    target_store_ids: list[int] = []
    can_view_recipients: bool = False
    id: int
    title: str
    content: str
    priority: str
    target_type: str
    department_id: int | None
    department_name: str | None
    publisher_id: int
    publisher_name: str
    starts_at: datetime
    deadline_at: datetime | None
    close_on_all_confirmed: bool
    status: str
    closed_at: datetime | None
    close_reason: str | None
    version: int
    created_at: datetime
    updated_at: datetime
    read_at: datetime | None
    confirmed_at: datetime | None
    recipient_count: int
    confirmed_count: int
    can_manage: bool
    can_confirm: bool


class ContactNoticeDetailResponse(ContactNoticeItemResponse):
    recipients: list[NoticeRecipientResponse]
    employee_ids: list[int]


# endregion


# region 分页和提醒
class ContactNoticeListResponse(BaseModel):
    items: list[ContactNoticeItemResponse]
    page: int
    page_size: int
    total: int
    total_pages: int


class ContactNoticeSummaryResponse(BaseModel):
    unread: int
    pending: int


# endregion
