"""操作审计记录查询 API 路由。"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies.auth import get_current_employee_id
from app.dependencies.db import get_db
from app.schemas.base import ResponseModel
from app.schemas.operation_audit_logs_requests import OperationAuditLogListRequest
from app.schemas.operation_audit_logs_responses import OperationAuditLogListResponse
from app.services.operation_audit_logs import get_operation_audit_logs_service

# 最终接口地址为 /api/v1/operation-audit-logs/list。
operation_audit_logs_router = APIRouter(
    prefix="/operation-audit-logs",
    tags=["operation-audit-logs"],
)


# region 获取操作审计记录列表接口
@operation_audit_logs_router.get(
    "/list",
    response_model=ResponseModel[OperationAuditLogListResponse],
    summary="获取操作审计记录",
    description="店长分页查询操作审计记录，并可按员工、模块、操作、目标和时间筛选。",
)
async def get_operation_audit_logs_list(
    request: OperationAuditLogListRequest = Depends(),
    current_employee_id: int = Depends(get_current_employee_id),
    db: AsyncSession = Depends(get_db),
) -> ResponseModel[OperationAuditLogListResponse]:
    """接收分页及筛选参数，并返回统一格式的操作审计记录列表。"""

    audit_logs = await get_operation_audit_logs_service(
        page=request.page,
        page_size=request.page_size,
        employee_id=request.employee_id,
        module=request.module,
        action=request.action,
        target_type=request.target_type,
        target_id=request.target_id,
        start_time=request.start_time,
        end_time=request.end_time,
        current_employee_id=current_employee_id,
        db=db,
    )

    return ResponseModel[OperationAuditLogListResponse](
        message="获取操作审计记录成功",
        data=audit_logs,
    )


# endregion


__all__ = ["operation_audit_logs_router"]
