"""销售记录接口的响应模型。"""

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


# region 销售单列表项
class SalesItemResponse(BaseModel):
    """销售单列表中的一张收银记录。"""

    sale_no: str = Field(..., description="销售单号", min_length=1, max_length=30)
    sold_at: datetime = Field(..., description="销售时间")
    total_amount: Decimal = Field(..., description="销售总金额", ge=0)
    total_quantity: int = Field(..., description="商品销售总数量", ge=0)
    item_count: int = Field(..., description="商品明细种类数", ge=0)

    model_config = ConfigDict(from_attributes=True)


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


__all__ = ["SalesItemResponse", "SalesListResponse"]
