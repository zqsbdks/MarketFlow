"""按完整营业日期统计废弃损耗，结束日期包含当天。"""

from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field


class DiscardAnalysisRequest(BaseModel):
    start_date: date
    end_date: date
    department_id: int | None = Field(None, ge=1)


class DiscardAnalysisGroup(BaseModel):
    key: str
    name: str
    quantity: int
    cost: Decimal
    cost_share: Decimal


class DiscardAnalysisResponse(BaseModel):
    record_count: int
    quantity: int
    cost: Decimal
    reasons: list[DiscardAnalysisGroup]
    departments: list[DiscardAnalysisGroup]
    stores: list[DiscardAnalysisGroup]
