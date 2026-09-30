"""AI 助手聊天请求模型。"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


# region AI聊天消息与请求
class AiChatMessageRequest(BaseModel):
    """发送给模型的一条用户或模型历史消息。"""

    role: Literal["user", "model"] = Field(..., description="消息发送方")
    content: str = Field(..., min_length=1, max_length=4000, description="消息正文")

    model_config = ConfigDict(str_strip_whitespace=True)


class AiChatRequest(BaseModel):
    """前端提交的一次 Gemini 多轮聊天请求。"""

    model: str = Field(
        "gemini-3.5-flash-lite",
        min_length=1,
        max_length=100,
        pattern=r"^[A-Za-z0-9._-]+$",
        description="Gemini模型名称",
    )
    messages: list[AiChatMessageRequest] = Field(
        ...,
        min_length=1,
        max_length=12,
        description="最近的聊天历史，最后一条必须是用户消息",
    )

    model_config = ConfigDict(str_strip_whitespace=True)


# endregion

__all__ = ["AiChatMessageRequest", "AiChatRequest"]
