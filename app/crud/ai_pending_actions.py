"""AI 待确认操作数据访问函数。"""

from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai_pending_action import AiPendingAction


# region 创建与查询待确认操作
async def create_ai_pending_action(
    *,
    employee_id: int,
    provider: str,
    action_type: str,
    arguments: dict[str, Any],
    summary: str,
    expires_at: datetime,
    db: AsyncSession,
) -> AiPendingAction:
    """把模型提出的修改保存为 pending；本函数不执行真实业务修改。"""

    action = AiPendingAction(
        employee_id=employee_id,
        store_id=db.info.get("read_store_id"),
        provider=provider,
        action_type=action_type,
        arguments=arguments,
        summary=summary,
        status="pending",
        expires_at=expires_at,
    )
    db.add(action)
    await db.flush()
    return action


async def get_ai_pending_action_by_id(
    *,
    action_id: int,
    db: AsyncSession,
    for_update: bool = False,
) -> AiPendingAction | None:
    """按ID读取操作；确认和取消时通过行锁防止重复点击并发执行。"""

    statement = select(AiPendingAction).where(AiPendingAction.id == action_id)
    if for_update:
        statement = statement.with_for_update()
    return (await db.execute(statement)).scalar_one_or_none()


# endregion

__all__ = ["create_ai_pending_action", "get_ai_pending_action_by_id"]
