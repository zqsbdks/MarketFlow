"""ai_conversations：数据库读写函数。"""

from sqlalchemy import select

from app.models.ai_conversation import AiMessage
from app.models.ai_pending_action import AiPendingAction


async def get_conversation_messages(db, before_id, item):
    """构建并执行get_conversation_query的查询，店铺条件在这里明确添加。"""
    query = select(AiMessage).where(AiMessage.conversation_id == item.id)
    if before_id:
        query = query.where(AiMessage.id < before_id)
    return await db.scalars(query.order_by(AiMessage.id.desc()).limit(100))


async def get_message_actions(db, action_ids, employee_id):
    """执行get_conversation_service所需的数据库查询；权限由调用它的服务检查。"""
    return await db.scalars(
        select(AiPendingAction).where(
            AiPendingAction.id.in_(action_ids), AiPendingAction.employee_id == employee_id
        )
    )
