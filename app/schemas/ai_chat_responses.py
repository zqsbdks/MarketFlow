"""AI 助手聊天响应模型。"""

from pydantic import BaseModel, Field


# region AI聊天响应
class AiChatResponse(BaseModel):
    """返回 Gemini 生成的回答以及实际使用的模型名称。"""

    message: str = Field(..., min_length=1, description="AI回答正文")
    model: str = Field(..., min_length=1, max_length=100, description="实际使用的模型名称")


# endregion

__all__ = ["AiChatResponse"]
