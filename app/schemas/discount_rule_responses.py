"""折扣规则与适用范围响应模型。"""

from datetime import datetime, time
from decimal import Decimal

from pydantic import BaseModel, Field

from app.models.enums import (
    DiscountComputedStatus,
    DiscountScheduleType,
    DiscountType,
    ProductStatus,
)


# region 折扣规则列表项响应模型
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
    is_active: bool = Field(..., description="人工启停开关")
    computed_status: DiscountComputedStatus = Field(..., description="后端动态计算状态")
    created_by: int = Field(..., ge=1, description="创建员工ID")
    created_by_name: str = Field(..., min_length=1, max_length=50, description="创建员工姓名")
    created_at: datetime = Field(..., description="创建时间")
    updated_at: datetime = Field(..., description="更新时间")


# endregion


# region 折扣规则分页列表响应模型
class DiscountRuleListResponse(BaseModel):
    """折扣规则分页列表及分页信息。"""

    items: list[DiscountRuleListItemResponse] = Field(..., description="折扣规则列表")
    page: int = Field(..., ge=1, description="当前页码")
    page_size: int = Field(..., ge=1, le=100, description="每页数量")
    total: int = Field(..., ge=0, description="符合条件的规则总数")
    total_pages: int = Field(..., ge=0, description="总页数")


# endregion


# region 添加折扣商品响应模型
class AddDiscountRuleProductsResponse(BaseModel):
    """向折扣规则批量添加商品后的响应。"""

    discount_rule_id: int = Field(..., ge=1, description="折扣规则ID")
    product_ids: list[int] = Field(..., description="本次成功添加的商品ID列表")


# endregion


# region 删除折扣商品响应模型
class DeleteDiscountRuleProductsResponse(BaseModel):
    """删除一件或多件折扣商品后的统一响应。"""

    discount_rule_id: int = Field(..., ge=1, description="折扣规则ID")
    deleted_count: int = Field(..., ge=0, description="本次删除的商品关联数量")
    deleted_product_ids: list[int] = Field(..., description="本次删除的商品ID列表")


# endregion


# region 折扣商品列表项响应模型
class DiscountRuleProductItemResponse(BaseModel):
    """折扣规则中的一条商品关联及价格信息。"""

    scope_id: int = Field(..., ge=1, description="折扣商品关联ID")
    discount_rule_id: int = Field(..., ge=1, description="折扣规则ID")
    product_id: int = Field(..., ge=1, description="商品ID")
    product_no: str = Field(..., min_length=1, max_length=20, description="商品编号")
    product_name: str = Field(..., min_length=1, max_length=100, description="商品名称")
    department_id: int = Field(..., ge=1, description="所属部门ID")
    department_name: str = Field(..., min_length=1, max_length=50, description="所属部门名称")
    category_id: int = Field(..., ge=1, description="所属分类ID")
    category_name: str = Field(..., min_length=1, max_length=50, description="所属分类名称")
    original_price: Decimal = Field(..., ge=0, decimal_places=2, description="商品原销售价")
    discount_type: DiscountType = Field(..., description="折扣计算方式")
    discount_value: Decimal = Field(..., gt=0, decimal_places=4, description="折扣数值")
    discounted_price: Decimal = Field(..., ge=0, decimal_places=2, description="计算后的折后价")
    product_status: ProductStatus = Field(..., description="商品销售状态")
    created_at: datetime = Field(..., description="商品加入折扣规则的时间")


# endregion


# region 折扣商品分页列表响应模型
class DiscountRuleProductListResponse(BaseModel):
    """某条折扣规则的商品列表及分页信息。"""

    items: list[DiscountRuleProductItemResponse] = Field(..., description="折扣商品列表")
    page: int = Field(..., ge=1, description="当前页码")
    page_size: int = Field(..., ge=1, le=100, description="每页数量")
    total: int = Field(..., ge=0, description="符合条件的折扣商品总数")
    total_pages: int = Field(..., ge=0, description="总页数")


# endregion


# region 折扣适用范围响应模型
# 后续添加：商品、分类或部门适用范围响应模型。
# endregion


__all__ = [
    "AddDiscountRuleProductsResponse",
    "DeleteDiscountRuleProductsResponse",
    "DiscountRuleListItemResponse",
    "DiscountRuleListResponse",
    "DiscountRuleProductItemResponse",
    "DiscountRuleProductListResponse",
]
