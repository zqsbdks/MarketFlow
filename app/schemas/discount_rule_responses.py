"""折扣规则与适用范围响应模型。"""

from datetime import datetime, time
from decimal import Decimal

from pydantic import BaseModel, Field

from app.models.enums import (
    DiscountComputedStatus,
    DiscountScheduleType,
    DiscountType,
)


# region 折扣规则列表响应模型
class DiscountRuleListItemResponse(BaseModel):
    """折扣规则列表中的一条完整规则。"""

    id: int = Field(..., ge=1, description="折扣规则ID")
    name: str = Field(..., min_length=1, max_length=100, description="折扣规则名称")
    discount_type: DiscountType = Field(..., description="折扣计算方式")
    discount_value: Decimal = Field(..., gt=0, decimal_places=4, description="折扣数值")
    schedule_type: DiscountScheduleType = Field(..., description="折扣执行周期")
    starts_at: datetime | None = Field(None, description="单次活动开始时间")
    ends_at: datetime | None = Field(None, description="单次活动结束时间")
    daily_start_time: time | None = Field(None, description="每日循环开始时间")
    daily_end_time: time | None = Field(None, description="每日循环结束时间")
    weekdays: list[int] | None = Field(None, description="每周执行日；1至7表示周一至周日")
    start_stock_threshold: int | None = Field(None, ge=0, description="开始打折库存阈值")
    end_stock_threshold: int | None = Field(None, ge=0, description="停止打折库存阈值")
    is_active: bool = Field(..., description="人工启停开关")
    computed_status: DiscountComputedStatus = Field(..., description="后端动态计算状态")
    created_by: int = Field(..., ge=1, description="创建员工ID")
    created_by_name: str = Field(..., min_length=1, max_length=50, description="创建员工姓名")
    created_at: datetime = Field(..., description="创建时间")
    updated_at: datetime = Field(..., description="更新时间")


class DiscountRuleListResponse(BaseModel):
    """折扣规则分页列表及分页信息。"""

    items: list[DiscountRuleListItemResponse] = Field(..., description="折扣规则列表")
    page: int = Field(..., ge=1, description="当前页码")
    page_size: int = Field(..., ge=1, le=100, description="每页数量")
    total: int = Field(..., ge=0, description="符合条件的规则总数")
    total_pages: int = Field(..., ge=0, description="总页数")


# endregion


# region 折扣适用范围响应模型
# 后续添加：商品、分类或部门适用范围响应模型。
# endregion


__all__ = ["DiscountRuleListItemResponse", "DiscountRuleListResponse"]
