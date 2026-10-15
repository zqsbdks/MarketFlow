"""当前账号的AI历史会话，任何角色均不能读取其他人的聊天。"""

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies.auth import get_verified_current_employee_id
from app.dependencies.db import get_db
from app.services.ai_conversations import get_conversation_service, list_conversations_service

ai_conversations_router = APIRouter(prefix="/ai-conversations", tags=["ai-conversations"])


# region 会话与完整消息
@ai_conversations_router.get("", summary="查询自己当前门店的AI会话")
async def list_conversations(
    employee_id: int = Depends(get_verified_current_employee_id),
    db: AsyncSession = Depends(get_db),
    *,
    http_request: Request,
):
    return await list_conversations_service(
        employee_id=employee_id, db=db, http_request=http_request
    )


@ai_conversations_router.get("/{conversation_id}", summary="恢复自己的AI对话")
async def get_conversation(
    conversation_id: int,
    before_id: int | None = None,
    employee_id: int = Depends(get_verified_current_employee_id),
    db: AsyncSession = Depends(get_db),
    *,
    http_request: Request,
):
    return await get_conversation_service(
        conversation_id=conversation_id,
        before_id=before_id,
        employee_id=employee_id,
        db=db,
        http_request=http_request,
    )


# endregion
