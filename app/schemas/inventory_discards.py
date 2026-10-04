"""商品废弃请求与响应；日期范围按日本营业日期包含首尾两天。"""

from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

DiscardReason = Literal["expired", "damaged", "spoiled", "contaminated", "other"]
ManualDiscardReason = Literal["damaged", "spoiled", "contaminated", "other"]


class DiscardPlanRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    product_id: int = Field(ge=1)
    quantity: int = Field(ge=1, le=1_000_000, strict=True)
    batch_id: int | None = Field(None, ge=1)


class DiscardCreateRequest(DiscardPlanRequest):
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
    page: int = Field(1, ge=1)
    page_size: int = Field(20, ge=1, le=100)
    product_id: int | None = Field(None, ge=1)
    department_id: int | None = Field(None, ge=1)
    reason_code: DiscardReason | None = None
    mode: Literal["automatic", "manual"] | None = None
    start_date: date | None = None
    end_date: date | None = None


class DiscardBatchResponse(BaseModel):
    batch_id: int
    batch_no: str
    expiration_date: date | None
    remaining_quantity: int
    unit_cost: Decimal


class DiscardStockResponse(BaseModel):
    product_id: int
    product_no: str
    product_name: str
    department_id: int
    department_name: str
    available_quantity: int
    batches: list[DiscardBatchResponse]


class DiscardItemResponse(BaseModel):
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
    product_id: int
    product_name: str
    quantity: int
    total_cost: Decimal
    items: list[DiscardItemResponse]


class DiscardResponse(BaseModel):
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
    items: list[DiscardResponse]
    page: int
    page_size: int
    total: int
    total_pages: int
    total_quantity: int
    total_cost: Decimal
