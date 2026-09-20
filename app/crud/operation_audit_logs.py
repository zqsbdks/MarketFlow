"""统一操作审计记录数据访问函数。"""

from typing import Any

from fastapi.encoders import jsonable_encoder
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.operation_audit_log import OperationAuditLog


async def create_operation_audit_log(
    *,
    employee_id: int | None,
    module: str,
    action: str,
    target_type: str,
    target_id: int,
    before_data: dict[str, Any] | None,
    after_data: dict[str, Any] | None,
    reason: str | None,
    db: AsyncSession,
) -> OperationAuditLog:
    """把一次数据变更加入当前事务；系统自动任务的员工 ID 可以为空。"""

    log = OperationAuditLog(
        employee_id=employee_id,
        module=module,
        action=action,
        target_type=target_type,
        target_id=target_id,
        before_data=jsonable_encoder(before_data),
        after_data=jsonable_encoder(after_data),
        reason=reason,
    )
    db.add(log)
    await db.flush()
    return log


__all__ = ["create_operation_audit_log"]
