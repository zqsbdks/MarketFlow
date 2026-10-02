"""AI 助手聊天、待确认操作与执行结果响应模型。"""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.ai_chat_requests import AiProviderName

AiActionStatus = Literal[
    "pending",
    "processing",
    "executed",
    "cancelled",
    "expired",
    "failed",
]


# region AI待确认操作响应
class AiPendingActionResponse(BaseModel):
    """展示给用户确认或取消的一次 AI 数据修改建议。"""

    id: int = Field(..., ge=1, description="待确认操作ID")
    action_type: str = Field(..., description="白名单操作类型")
    summary: str = Field(..., description="修改内容预览")
    arguments: dict[str, Any] = Field(..., description="经过后端校验的操作参数")
    status: AiActionStatus = Field(..., description="操作当前状态")
    expires_at: datetime = Field(..., description="确认截止时间")
    executed_at: datetime | None = Field(None, description="执行完成时间")
    failure_reason: str | None = Field(None, description="失败原因")

    model_config = ConfigDict(from_attributes=True)


# endregion


# region AI聊天响应
class AiChatResponse(BaseModel):
    conversation_id: int | None = None
    """返回模型回答，以及本轮产生的待确认数据修改。"""

    message: str = Field(..., min_length=1, description="AI回答正文")
    provider: AiProviderName = Field(..., description="实际使用的模型供应商")
    model: str = Field(..., min_length=1, max_length=100, description="实际使用的模型ID")
    pending_actions: list[AiPendingActionResponse] = Field(
        default_factory=list,
        description="必须由当前员工二次确认的修改操作",
    )


class AiActionExecutionResponse(BaseModel):
    """确认或取消待处理操作后的结果。"""

    action: AiPendingActionResponse = Field(..., description="最新操作状态")
    result: dict[str, Any] | None = Field(None, description="成功执行后的业务结果")


# endregion

__all__ = [
    "AiActionExecutionResponse",
    "AiActionStatus",
    "AiChatResponse",
    "AiPendingActionResponse",
]
