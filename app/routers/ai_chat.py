"""多模型AI助手、实时工具调用与修改确认API路由。"""

from typing import Annotated

from fastapi import APIRouter, Depends, Header, Path
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies.auth import get_verified_current_employee_id
from app.dependencies.db import get_db
from app.schemas.ai_chat_requests import AiChatRequest, AiProviderName
from app.schemas.ai_chat_responses import AiActionExecutionResponse, AiChatResponse
from app.schemas.base import ResponseModel
from app.services.ai_actions import cancel_ai_action_service, confirm_ai_action_service
from app.services.ai_chat import ai_chat_service
from app.services.ai_credentials import (
    delete_ai_credential,
    has_ai_credential,
    read_ai_credential,
    save_ai_credential,
)

ai_chat_router = APIRouter(prefix="/ai-chat", tags=["ai-chat"])

AiApiKeyHeader = Annotated[
    str | None,
    Header(
        alias="X-AI-Api-Key",
        max_length=255,
        description="兼容旧客户端；不传则使用当前员工已加密保存的 Key",
    ),
]


class AiCredentialRequest(BaseModel):
    """配置员工自己的模型供应商密钥。"""

    api_key: str = Field(..., min_length=10, max_length=255)


# region AI实时聊天接口
@ai_chat_router.post(
    "",
    response_model=ResponseModel[AiChatResponse],
    summary="与AI业务助手聊天",
    description="支持Gemini和OpenAI，并允许AI调用受控的MarketFlow实时查询工具。",
)
async def chat_with_ai(
    request: AiChatRequest,
    api_key: AiApiKeyHeader = None,
    current_employee_id: int = Depends(get_verified_current_employee_id),
    db: AsyncSession = Depends(get_db),
) -> ResponseModel[AiChatResponse]:
    """验证账号后调用模型；查询可直接执行，修改只生成待确认操作。"""

    resolved_key = api_key or await read_ai_credential(current_employee_id, request.provider, db)
    result = await ai_chat_service(
        request=request,
        api_key=resolved_key,
        current_employee_id=current_employee_id,
        db=db,
    )
    return ResponseModel[AiChatResponse](message="AI回答成功", data=result)


# endregion


@ai_chat_router.get("/credentials/{provider}", response_model=ResponseModel[dict[str, bool]])
async def get_ai_credential_status(
    provider: AiProviderName,
    current_employee_id: int = Depends(get_verified_current_employee_id),
    db: AsyncSession = Depends(get_db),
) -> ResponseModel[dict[str, bool]]:
    """只返回当前员工是否配置了该供应商的密钥。"""

    configured = await has_ai_credential(current_employee_id, provider, db)
    return ResponseModel(data={"configured": configured})


@ai_chat_router.put("/credentials/{provider}", response_model=ResponseModel[dict[str, bool]])
async def put_ai_credential(
    provider: AiProviderName,
    request: AiCredentialRequest,
    current_employee_id: int = Depends(get_verified_current_employee_id),
    db: AsyncSession = Depends(get_db),
) -> ResponseModel[dict[str, bool]]:
    """加密保存当前员工的 API Key。"""

    await save_ai_credential(current_employee_id, provider, request.api_key, db)
    return ResponseModel(data={"configured": True})


@ai_chat_router.delete("/credentials/{provider}", response_model=ResponseModel[dict[str, bool]])
async def remove_ai_credential(
    provider: AiProviderName,
    current_employee_id: int = Depends(get_verified_current_employee_id),
    db: AsyncSession = Depends(get_db),
) -> ResponseModel[dict[str, bool]]:
    """移除当前员工保存的 API Key。"""

    await delete_ai_credential(current_employee_id, provider, db)
    return ResponseModel(data={"configured": False})


# region 确认与取消AI修改
@ai_chat_router.post(
    "/actions/{action_id}/confirm",
    response_model=ResponseModel[AiActionExecutionResponse],
    summary="确认执行AI提出的修改",
    description="重新验证当前员工权限和最新业务状态后，执行一次待确认操作。",
)
async def confirm_ai_action(
    action_id: int = Path(..., ge=1, description="待确认操作ID"),
    current_employee_id: int = Depends(get_verified_current_employee_id),
    db: AsyncSession = Depends(get_db),
) -> ResponseModel[AiActionExecutionResponse]:
    """只有发起操作的员工可以确认；同一操作无法重复执行。"""

    result = await confirm_ai_action_service(
        action_id=action_id,
        employee_id=current_employee_id,
        db=db,
    )
    return ResponseModel[AiActionExecutionResponse](message="AI操作执行成功", data=result)


@ai_chat_router.post(
    "/actions/{action_id}/cancel",
    response_model=ResponseModel[AiActionExecutionResponse],
    summary="取消AI提出的修改",
    description="取消本人尚未执行的AI待确认操作，不修改任何业务数据。",
)
async def cancel_ai_action(
    action_id: int = Path(..., ge=1, description="待确认操作ID"),
    current_employee_id: int = Depends(get_verified_current_employee_id),
    db: AsyncSession = Depends(get_db),
) -> ResponseModel[AiActionExecutionResponse]:
    """将等待确认的操作标记为取消。"""

    result = await cancel_ai_action_service(
        action_id=action_id,
        employee_id=current_employee_id,
        db=db,
    )
    return ResponseModel[AiActionExecutionResponse](message="AI操作已取消", data=result)


# endregion

__all__ = ["ai_chat_router"]
