"""AI 助手多供应商聊天与操作请求模型。"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

AiProviderName = Literal["gemini", "openai"]


# region AI聊天请求模型
class AiChatMessageRequest(BaseModel):
    """一条用户或模型历史消息。"""

    role: Literal["user", "model"] = Field(..., description="消息发送方")
    content: str = Field(..., min_length=1, max_length=4000, description="消息正文")

    model_config = ConfigDict(str_strip_whitespace=True)


class AiChatRequest(BaseModel):
    conversation_id: int | None = Field(None, ge=1, description="继续已保存的会话；不传则新建")
    """一次支持工具调用的多轮 AI 聊天请求。"""

    provider: AiProviderName = Field("gemini", description="模型供应商")
    model: str | None = Field(
        None,
        min_length=1,
        max_length=100,
        pattern=r"^[A-Za-z0-9._-]+$",
        description="模型ID；不传时使用该供应商默认模型",
    )
    messages: list[AiChatMessageRequest] = Field(
        ...,
        min_length=1,
        max_length=40,
        description="最近12条聊天记录；最后一条必须来自用户",
    )

    model_config = ConfigDict(str_strip_whitespace=True)


# endregion

__all__ = ["AiChatMessageRequest", "AiChatRequest", "AiProviderName"]
