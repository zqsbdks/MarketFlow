"""按完整营业日期统计废弃损耗，结束日期包含当天。"""

from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field


class DiscardAnalysisRequest(BaseModel):
    """损耗查询起止日期和可选部门，按日本业务时间的完整日统计。"""

    start_date: date
    end_date: date
    department_id: int | None = Field(None, ge=1)


class DiscardAnalysisGroup(BaseModel):
    """原因、部门或门店的损耗数量、成本与成本占比。"""

    key: str
    name: str
    quantity: int
    cost: Decimal
    cost_share: Decimal


class DiscardAnalysisResponse(BaseModel):
    """损耗总量及可选分组；成本不自动扣入销售毛利润。"""

    record_count: int
    quantity: int
    cost: Decimal
    reasons: list[DiscardAnalysisGroup]
    departments: list[DiscardAnalysisGroup]
    stores: list[DiscardAnalysisGroup]
