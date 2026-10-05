"""联络事项列表、详情和确认名单响应。"""

from datetime import datetime

from pydantic import BaseModel


# region 事项和接收员工
class NoticeRecipientResponse(BaseModel):
    """接收员工及其阅读、确认信息，普通员工不能据此查询他人状态。"""

    store_id: int | None = None
    employee_id: int
    name: str
    department_name: str | None
    read_at: datetime | None
    confirmed_at: datetime | None
    light: str


class ContactNoticeItemResponse(BaseModel):
    """事项列表概要，详细正文与名单通过详情接口返回。"""

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
    """事项详情及授权可见的接收确认名单。"""

    recipients: list[NoticeRecipientResponse]
    employee_ids: list[int]


# endregion


# region 分页和提醒
class ContactNoticeListResponse(BaseModel):
    """分页事项列表及总量，分页统计与记录使用一致权限条件。"""

    items: list[ContactNoticeItemResponse]
    page: int
    page_size: int
    total: int
    total_pages: int


class ContactNoticeSummaryResponse(BaseModel):
    """当前账号未读与待确认事项的摘要，用于导航提醒。"""

    unread: int
    pending: int


# endregion
