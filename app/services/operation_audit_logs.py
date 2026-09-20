"""操作审计记录查询业务逻辑。"""

from datetime import datetime

from fastapi import HTTPException
from fastapi import status as http_status
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.auth import get_employee_by_id
from app.crud.operation_audit_logs import get_operation_audit_logs
from app.models.enums import EmployeeRole
from app.schemas.operation_audit_logs_responses import (
    OperationAuditLogItemResponse,
    OperationAuditLogListResponse,
)


# region 获取操作审计记录列表
async def get_operation_audit_logs_service(
    page: int,
    page_size: int,
    employee_id: int | None,
    module: str | None,
    action: str | None,
    target_type: str | None,
    target_id: int | None,
    start_time: datetime | None,
    end_time: datetime | None,
    current_employee_id: int,
    db: AsyncSession,
) -> OperationAuditLogListResponse:
    """验证店长权限和时间范围，并组装分页审计记录列表。"""

    # 审计数据包含员工操作和修改前后内容，只允许账号状态正常的店长查看。
    current_employee = await get_employee_by_id(employee_id=current_employee_id, db=db)
    if current_employee is None:
        raise HTTPException(
            status_code=http_status.HTTP_401_UNAUTHORIZED,
            detail="当前登录员工不存在",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not current_employee.is_active:
        raise HTTPException(status_code=http_status.HTTP_403_FORBIDDEN, detail="账号已停用")
    if current_employee.must_change_password:
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail="请先修改初始密码",
        )
    if current_employee.role != EmployeeRole.STORE_MANAGER:
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail="只有店长可以查看操作审计记录",
        )

    if start_time is not None and end_time is not None and start_time > end_time:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail="开始时间不能晚于结束时间",
        )

    offset = (page - 1) * page_size
    audit_logs, total = await get_operation_audit_logs(
        offset=offset,
        page_size=page_size,
        employee_id=employee_id,
        module=module,
        action=action,
        target_type=target_type,
        target_id=target_id,
        start_time=start_time,
        end_time=end_time,
        db=db,
    )

    # employee_id 为空的记录来自定时任务，使用明确名称方便前端直接显示。
    items: list[OperationAuditLogItemResponse] = []
    for audit_log, employee_name in audit_logs:
        items.append(
            OperationAuditLogItemResponse(
                id=audit_log.id,
                employee_id=audit_log.employee_id,
                employee_name=employee_name or "系统自动任务",
                module=audit_log.module,
                action=audit_log.action,
                target_type=audit_log.target_type,
                target_id=audit_log.target_id,
                before_data=audit_log.before_data,
                after_data=audit_log.after_data,
                reason=audit_log.reason,
                created_at=audit_log.created_at,
            )
        )

    return OperationAuditLogListResponse(
        items=items,
        page=page,
        page_size=page_size,
        total=total,
        total_pages=(total + page_size - 1) // page_size,
    )


# endregion


__all__ = ["get_operation_audit_logs_service"]
