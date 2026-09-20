"""操作审计记录查询接口的请求模型。"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# 库存流水只包含真正改变批次数量的四种操作。
InventoryMovementAction = Literal[
    "create_batch",
    "sale_deduction",
    "update_quantity",
    "discard_expired",
]


# region 操作审计记录列表请求模型
class OperationAuditLogListRequest(BaseModel):
    """审计记录列表的分页参数和可选筛选条件。"""

    page: int = Field(1, description="当前页码", ge=1)
    page_size: int = Field(20, description="每页数量", ge=1, le=100)
    employee_id: int | None = Field(None, description="操作员工ID", ge=1)
    module: str | None = Field(None, description="业务模块", min_length=1, max_length=50)
    action: str | None = Field(None, description="操作类型", min_length=1, max_length=50)
    target_type: str | None = Field(None, description="目标类型", min_length=1, max_length=50)
    target_id: int | None = Field(None, description="目标记录ID", ge=1)
    start_time: datetime | None = Field(None, description="操作开始时间，包含该时刻")
    end_time: datetime | None = Field(None, description="操作结束时间，包含该时刻")

    # 自动去掉模块、操作类型和目标类型两端的空格。
    model_config = ConfigDict(str_strip_whitespace=True)


# endregion


# region 库存变动流水请求模型
class InventoryMovementListRequest(BaseModel):
    """库存变动流水的分页和筛选参数。"""

    page: int = Field(1, description="当前页码", ge=1)
    page_size: int = Field(20, description="每页数量", ge=1, le=100)
    keyword: str | None = Field(
        None,
        description="商品名称、商品编号或批次号关键词",
        min_length=1,
        max_length=100,
    )
    action: InventoryMovementAction | None = Field(None, description="库存变动类型")
    batch_id: int | None = Field(None, description="库存批次ID", ge=1)
    product_id: int | None = Field(None, description="商品ID", ge=1)
    start_time: datetime | None = Field(None, description="开始时间，包含该时刻")
    end_time: datetime | None = Field(None, description="结束时间，包含该时刻")

    model_config = ConfigDict(str_strip_whitespace=True)


# endregion


__all__ = [
    "InventoryMovementAction",
    "InventoryMovementListRequest",
    "OperationAuditLogListRequest",
]
