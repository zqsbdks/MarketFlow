"""ai_memory：数据库读写函数。"""

from sqlalchemy import or_, select

from app.models.ai_conversation import AiConversation, AiMessage
from app.models.employee import Employee


async def get_owned_conversation(db, conversation_id, employee_id, lock):
    """构建并执行owned_conversation_query的查询，店铺条件在这里明确添加。"""
    query = select(AiConversation).where(
        AiConversation.id == conversation_id, AiConversation.employee_id == employee_id
    )
    if lock:
        query = query.with_for_update()
    return await db.scalar(query)


async def get_conversation_owner(db, employee_id):
    """执行owned_conversation所需的数据库查询；权限由调用它的服务检查。"""
    return await db.get(Employee, employee_id)


async def get_list_owner(db, employee_id):
    """执行conversation_list所需的数据库查询；权限由调用它的服务检查。"""
    return await db.get(Employee, employee_id)


async def get_employee_conversations(db, employee, employee_id):
    """执行conversation_list所需的数据库查询；权限由调用它的服务检查。"""
    return await db.scalars(
        select(AiConversation)
        .where(
            AiConversation.employee_id == employee_id,
            AiConversation.store_id == db.info.get("read_store_id"),
            AiConversation.home_store_id == employee.store_id,
        )
        .order_by(AiConversation.updated_at.desc(), AiConversation.id.desc())
        .limit(100)
    )


def add_user_message(db, user_message):
    """执行persistent_ai_chat_service所需的数据库新增；权限由调用它的服务检查。"""
    return db.add(user_message)


def add_assistant_message(db, actions, conversation, result):
    """执行persistent_ai_chat_service所需的数据库新增；权限由调用它的服务检查。"""
    return db.add(
        AiMessage(
            conversation_id=conversation.id, role="model", content=result.message, actions=actions
        )
    )


async def get_chat_employee(db, current_employee_id):
    """执行persistent_ai_chat_service所需的数据库查询；权限由调用它的服务检查。"""
    return await db.get(Employee, current_employee_id)


def add_conversation(db, conversation):
    """执行persistent_ai_chat_service所需的数据库新增；权限由调用它的服务检查。"""
    return db.add(conversation)


async def get_older_messages(db, conversation, first_id):
    """执行persistent_ai_chat_service所需的数据库查询；权限由调用它的服务检查。"""
    return await db.scalars(
        select(AiMessage)
        .where(
            AiMessage.conversation_id == conversation.id,
            AiMessage.id < first_id,
            AiMessage.id > (conversation.summary_through_id or 0),
        )
        .order_by(AiMessage.id)
        .limit(40)
    )


async def get_recent_messages(db, conversation):
    """执行persistent_ai_chat_service所需的数据库查询；权限由调用它的服务检查。"""
    return await db.scalars(
        select(AiMessage)
        .where(AiMessage.conversation_id == conversation.id, AiMessage.role.in_(["user", "model"]))
        .order_by(AiMessage.id.desc())
        .limit(40)
    )


async def get_relevant_messages(db, conversation, first_id, terms):
    """构建并执行persistent_ai_chat_query_3的查询，店铺条件在这里明确添加。"""
    conditions = []
    for term in list(dict.fromkeys(terms))[:12]:
        conditions.append(AiMessage.content.contains(term, autoescape=True))
    return await db.scalars(
        select(AiMessage)
        .where(
            AiMessage.conversation_id == conversation.id, AiMessage.id < first_id, or_(*conditions)
        )
        .order_by(AiMessage.id.desc())
        .limit(4)
    )
