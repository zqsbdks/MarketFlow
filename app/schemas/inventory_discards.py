"""商品废弃请求与响应；日期范围按日本营业日期包含首尾两天。"""

from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

DiscardReason = Literal["expired", "damaged", "spoiled", "contaminated", "other"]
ManualDiscardReason = Literal["damaged", "spoiled", "contaminated", "other"]


class DiscardPlanRequest(BaseModel):
    """废弃预览数量与可选批次，只描述意图，不代表库存已锁定。"""

    model_config = ConfigDict(extra="forbid")
    product_id: int = Field(ge=1)
    quantity: int = Field(ge=1, le=1_000_000, strict=True)
    batch_id: int | None = Field(None, ge=1)


class DiscardCreateRequest(DiscardPlanRequest):
    """带请求ID和废弃原因的真实提交；同一ID不能改作其他废弃操作。"""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    request_id: UUID
    reason_code: ManualDiscardReason
    note: str | None = Field(None, min_length=1, max_length=255)

    @model_validator(mode="after")
    def require_other_note(self):
        if self.reason_code == "other" and not self.note:
            raise ValueError("其他原因必须填写说明")
        return self


class DiscardListRequest(BaseModel):
    """废弃记录日期、商品、部门和原因筛选及分页参数。"""

    page: int = Field(1, ge=1)
    page_size: int = Field(20, ge=1, le=100)
    product_id: int | None = Field(None, ge=1)
    department_id: int | None = Field(None, ge=1)
    reason_code: DiscardReason | None = None
    mode: Literal["automatic", "manual"] | None = None
    start_date: date | None = None
    end_date: date | None = None


class DiscardBatchResponse(BaseModel):
    """可处理批次的剩余数量、到期日期及实际进货成本。"""

    batch_id: int
    batch_no: str
    expiration_date: date | None
    remaining_quantity: int
    unit_cost: Decimal


class DiscardStockResponse(BaseModel):
    """指定商品可处理的批次清单及可用总量。"""

    product_id: int
    product_no: str
    product_name: str
    department_id: int
    department_name: str
    available_quantity: int
    batches: list[DiscardBatchResponse]


class DiscardItemResponse(BaseModel):
    """单批次废弃数量、成本及前后库存快照。"""

    model_config = ConfigDict(from_attributes=True)
    batch_id: int
    batch_no: str
    expiration_date: date | None
    quantity: int
    unit_cost: Decimal
    total_cost: Decimal
    before_quantity: int
    after_quantity: int


class DiscardPlanResponse(BaseModel):
    """废弃预览结果，提交前仍须重新检查库存和权限。"""

    product_id: int
    product_name: str
    quantity: int
    total_cost: Decimal
    items: list[DiscardItemResponse]


class DiscardResponse(BaseModel):
    """已保存废弃单和明细，不以当前商品售价覆盖历史成本。"""

    model_config = ConfigDict(from_attributes=True)
    id: int
    store_id: int
    product_id: int
    product_no: str
    product_name: str
    department_id: int
    department_name: str
    employee_id: int | None
    employee_name: str | None
    reason_code: DiscardReason
    note: str | None
    quantity: int
    total_cost: Decimal
    created_at: datetime
    items: list[DiscardItemResponse]


class DiscardListResponse(BaseModel):
    """废弃记录分页结果及汇总，遵循所选门店读取范围。"""

    items: list[DiscardResponse]
    page: int
    page_size: int
    total: int
    total_pages: int
    total_quantity: int
    total_cost: Decimal
