"""联络事项查询、发布和修改请求模型。"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


# region 查询请求
class ContactNoticeListRequest(BaseModel):
    """事项分页、状态和查看视角筛选，服务层再限制当前员工可见范围。"""

    source: Literal["store", "headquarters"] | None = None
    page: int = Field(1, ge=1)
    page_size: int = Field(10, ge=1, le=100)
    view: Literal["received", "published", "management"] = "received"
    target_type: Literal["all", "department", "personal"] | None = None
    status: Literal["draft", "published", "closed", "withdrawn"] | None = None
    keyword: str | None = Field(None, max_length=100)
    confirmed: bool | None = None
    read: bool | None = None
    priority: Literal["normal", "important", "urgent"] | None = None
    department_id: int | None = Field(None, ge=1)
    publisher_id: int | None = Field(None, ge=1)
    overdue: bool | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None


# endregion


# region 创建和修改请求
class ContactNoticeWriteRequest(BaseModel):
    """事项正文、接收范围、截止时间及全员确认关闭设置。"""

    store_ids: list[int] = Field(default_factory=list, max_length=100)
    model_config = ConfigDict(str_strip_whitespace=True)
    title: str = Field(..., min_length=1, max_length=100)
    content: str = Field(..., min_length=1, max_length=10000)
    priority: Literal["normal", "important", "urgent"] = "normal"
    target_type: Literal["all", "department", "personal"]
    department_id: int | None = Field(None, ge=1)
    employee_ids: list[int] = Field(default_factory=list, max_length=500)
    starts_at: datetime | None = None
    deadline_at: datetime | None = None
    close_on_all_confirmed: bool = True
    reason: str | None = Field(None, max_length=500)


class ContactNoticeUpdateRequest(ContactNoticeWriteRequest):
    """事项修改请求，版本及可编辑状态需由服务层验证。"""

    expected_version: int = Field(..., ge=1)


# endregion


# region 状态变更请求
class ContactNoticeActionRequest(BaseModel):
    """发布、撤回、关闭等操作请求，不能绕过事项状态和员工权限。"""

    expected_version: int = Field(..., ge=1)
    reason: str | None = Field(None, max_length=500)


# endregion
