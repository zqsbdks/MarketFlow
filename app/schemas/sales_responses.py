"""销售记录接口的响应模型。"""

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import DiscountType


# region 销售单列表项
class SalesItemResponse(BaseModel):
    """销售单列表中的一张收银记录。"""

    sale_no: str = Field(..., description="销售单号", min_length=1, max_length=30)
    sold_at: datetime = Field(..., description="销售时间")
    original_total_amount: Decimal = Field(..., description="折扣前商品原价总金额", ge=0)
    discount_amount: Decimal = Field(..., description="整张销售单优惠总金额", ge=0)
    total_amount: Decimal = Field(..., description="折扣后实际销售总金额", ge=0)
    total_quantity: int = Field(..., description="商品销售总数量", ge=0)
    item_count: int = Field(..., description="商品明细种类数", ge=0)

    model_config = ConfigDict(from_attributes=True)


# endregion


# region 销售单商品详情
class SaleDetailItemResponse(BaseModel):
    """销售单详情中的单个商品信息。"""

    product_id: int = Field(..., description="商品ID", ge=1)
    product_name: str = Field(
        ...,
        description="成交时商品名称",
        min_length=1,
        max_length=100,
    )
    quantity: int = Field(..., description="销售数量", ge=1)
    original_unit_price: Decimal = Field(..., description="成交前商品原销售单价", ge=0)
    unit_price: Decimal = Field(..., description="折扣后实际成交单价", ge=0)
    original_subtotal: Decimal = Field(..., description="本条明细折扣前原价小计", ge=0)
    discount_amount: Decimal = Field(..., description="本条明细优惠总金额", ge=0)
    subtotal: Decimal = Field(..., description="本条明细折扣后成交小计", ge=0)
    discount_rule_id: int | None = Field(None, description="成交时使用的折扣规则ID", ge=1)
    discount_rule_name: str | None = Field(
        None,
        description="成交时折扣规则名称快照",
        max_length=100,
    )
    discount_type: DiscountType | None = Field(None, description="成交时折扣计算方式快照")
    discount_value: Decimal | None = Field(
        None,
        description="成交时折扣数值快照",
        gt=0,
        decimal_places=4,
    )

    model_config = ConfigDict(from_attributes=True)


# endregion


# region 销售单详情响应
class SaleDetailResponse(BaseModel):
    """包含商品明细的一张销售单详情。"""

    sale_no: str = Field(..., description="销售单号", min_length=1, max_length=30)
    sold_at: datetime = Field(..., description="销售时间")
    original_total_amount: Decimal = Field(..., description="折扣前商品原价总金额", ge=0)
    discount_amount: Decimal = Field(..., description="整张销售单优惠总金额", ge=0)
    total_amount: Decimal = Field(..., description="折扣后实际销售总金额", ge=0)
    items: list[SaleDetailItemResponse] = Field(..., description="销售商品明细")

    model_config = ConfigDict(from_attributes=True)


# endregion


# region 销售价格预览响应
class SalePricePreviewResponse(BaseModel):
    """收银台结账前按照当前折扣计算出的整单价格。"""

    original_total_amount: Decimal = Field(..., description="折扣前商品原价总金额", ge=0)
    discount_amount: Decimal = Field(..., description="预计优惠总金额", ge=0)
    total_amount: Decimal = Field(..., description="预计实际支付总金额", ge=0)
    items: list[SaleDetailItemResponse] = Field(..., description="商品价格预览明细")


# endregion


# region 销售单列表响应
class SalesListResponse(BaseModel):
    """销售单列表及分页信息。"""

    items: list[SalesItemResponse] = Field(..., description="销售单列表")
    page: int = Field(..., description="当前页码", ge=1)
    page_size: int = Field(..., description="每页数量", ge=1, le=100)
    total: int = Field(..., description="销售单总数", ge=0)
    total_pages: int = Field(..., description="总页数", ge=0)

    model_config = ConfigDict(from_attributes=True)


# endregion


__all__ = [
    "SaleDetailItemResponse",
    "SaleDetailResponse",
    "SalePricePreviewResponse",
    "SalesItemResponse",
    "SalesListResponse",
]
