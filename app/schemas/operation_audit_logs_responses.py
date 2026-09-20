"""操作审计记录查询接口的响应模型。"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


# region 操作审计记录列表项响应模型
class OperationAuditLogItemResponse(BaseModel):
    """操作审计记录列表中的一条数据。"""

    id: int = Field(..., description="审计记录ID", ge=1)
    employee_id: int | None = Field(None, description="操作员工ID；系统任务为null", ge=1)
    employee_name: str = Field(..., description="操作员工姓名；系统任务显示系统自动任务")
    module: str = Field(..., description="业务模块", min_length=1, max_length=50)
    action: str = Field(..., description="操作类型", min_length=1, max_length=50)
    target_type: str = Field(..., description="目标类型", min_length=1, max_length=50)
    target_id: int = Field(..., description="目标记录ID", ge=1)
    before_data: dict[str, Any] | None = Field(None, description="修改前的数据")
    after_data: dict[str, Any] | None = Field(None, description="修改后的数据")
    reason: str | None = Field(None, description="操作或修改理由", max_length=255)
    created_at: datetime = Field(..., description="操作时间")

    model_config = ConfigDict(from_attributes=True)


# endregion


# region 操作审计记录分页响应模型
class OperationAuditLogListResponse(BaseModel):
    """操作审计记录列表及分页信息。"""

    items: list[OperationAuditLogItemResponse] = Field(..., description="操作审计记录列表")
    page: int = Field(..., description="当前页码", ge=1)
    page_size: int = Field(..., description="每页数量", ge=1, le=100)
    total: int = Field(..., description="符合条件的记录总数", ge=0)
    total_pages: int = Field(..., description="总页数", ge=0)


# endregion


__all__ = ["OperationAuditLogItemResponse", "OperationAuditLogListResponse"]
