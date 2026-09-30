"""Gemini AI 基础聊天 API 路由。"""

from typing import Annotated

from fastapi import APIRouter, Depends, Header

from app.dependencies.auth import get_verified_current_employee_id
from app.schemas.ai_chat_requests import AiChatRequest
from app.schemas.ai_chat_responses import AiChatResponse
from app.schemas.base import ResponseModel
from app.services.ai_chat import ai_chat_service

ai_chat_router = APIRouter(prefix="/ai-chat", tags=["ai-chat"])


# region AI基础问答接口
@ai_chat_router.post(
    "",
    response_model=ResponseModel[AiChatResponse],
    summary="与AI基础助手聊天",
    description="使用当前用户提供的Gemini API Key回答MarketFlow基础使用问题；密钥不会保存。",
)
async def chat_with_ai(
    request: AiChatRequest,
    api_key: Annotated[
        str,
        Header(
            alias="X-Gemini-Api-Key",
            min_length=10,
            max_length=255,
            description="当前用户自己的Gemini API Key",
        ),
    ],
    _current_employee_id: int = Depends(get_verified_current_employee_id),
) -> ResponseModel[AiChatResponse]:
    """验证登录账号并把本次聊天安全转发给 Gemini。"""

    result = await ai_chat_service(request=request, api_key=api_key)
    return ResponseModel[AiChatResponse](message="AI回答成功", data=result)


# endregion

__all__ = ["ai_chat_router"]
