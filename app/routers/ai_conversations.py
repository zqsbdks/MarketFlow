"""当前账号的AI历史会话，任何角色均不能读取其他人的聊天。"""

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies.auth import get_verified_current_employee_id
from app.dependencies.db import get_db
from app.models.ai_conversation import AiMessage
from app.models.ai_pending_action import AiPendingAction
from app.schemas.base import ResponseModel
from app.services.ai_memory import conversation_list, owned_conversation

ai_conversations_router = APIRouter(prefix="/ai-conversations", tags=["ai-conversations"])


# region 会话与完整消息
@ai_conversations_router.get("", summary="查询自己当前门店的AI会话")
async def list_conversations(
    employee_id: int = Depends(get_verified_current_employee_id), db: AsyncSession = Depends(get_db)
):
    conversations = await conversation_list(employee_id, db)
    return ResponseModel(
        data=[
            {
                "id": item.id,
                "title": item.title,
                "provider": item.provider,
                "model": item.model,
                "store_id": item.store_id,
            }
            for item in conversations
        ]
    )


@ai_conversations_router.get("/{conversation_id}", summary="恢复自己的AI对话")
async def get_conversation(
    conversation_id: int,
    before_id: int | None = None,
    employee_id: int = Depends(get_verified_current_employee_id),
    db: AsyncSession = Depends(get_db),
):
    item = await owned_conversation(conversation_id, employee_id, db)
    query = select(AiMessage).where(AiMessage.conversation_id == item.id)
    if before_id:
        query = query.where(AiMessage.id < before_id)
    messages = list((await db.scalars(query.order_by(AiMessage.id.desc()).limit(100))).all())
    messages.reverse()
    action_ids = []
    for message in messages:
        for action in message.actions or []:
            action_ids.append(action["id"])
    latest_actions = {}
    if action_ids:
        rows = (
            await db.scalars(
                select(AiPendingAction).where(
                    AiPendingAction.id.in_(action_ids), AiPendingAction.employee_id == employee_id
                )
            )
        ).all()
        for action in rows:
            latest_actions[action.id] = action
    serialized = []
    for message in messages:
        actions = []
        for original in message.actions or []:
            current = latest_actions.get(original["id"])
            if current is not None:
                actions.append(
                    {
                        "id": current.id,
                        "action_type": current.action_type,
                        "summary": current.summary,
                        "arguments": current.arguments,
                        "status": current.status,
                        "expires_at": current.expires_at,
                        "executed_at": current.executed_at,
                        "failure_reason": current.failure_reason,
                    }
                )
        serialized.append(
            {"id": message.id, "role": message.role, "content": message.content, "actions": actions}
        )
    return ResponseModel(
        data={
            "id": item.id,
            "title": item.title,
            "provider": item.provider,
            "model": item.model,
            "messages": serialized,
            "next_before_id": messages[0].id if len(messages) == 100 else None,
        }
    )


# endregion
