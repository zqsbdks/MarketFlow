"""供应商商品目录接口的响应模型。"""

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


# region 供应商商品列表项
class SupplierProductItemResponse(BaseModel):
    """供应商商品目录中的一件商品。"""

    id: int = Field(..., description="供应商商品目录ID", ge=1)
    supplier_id: int = Field(..., description="供应商ID", ge=1)
    supplier_name: str = Field(..., description="供应商名称", min_length=1, max_length=100)
    name: str = Field(..., description="供应商商品名称", min_length=1, max_length=100)
    unit_cost: Decimal = Field(..., description="当前默认进货单价", ge=0, decimal_places=2)
    shelf_life_days: int | None = Field(None, description="默认保质期天数", ge=1)
    is_active: bool = Field(..., description="是否仍在供应")
    created_at: datetime = Field(..., description="创建时间")
    updated_at: datetime = Field(..., description="更新时间")

    # 允许响应模型从SQLAlchemy对象的属性读取数据。
    model_config = ConfigDict(from_attributes=True)


# endregion


# region 供应商商品列表响应
class SupplierProductListResponse(BaseModel):
    """供应商商品列表及分页信息。"""

    items: list[SupplierProductItemResponse] = Field(..., description="供应商商品列表")
    page: int = Field(..., description="当前页码", ge=1)
    page_size: int = Field(..., description="每页数量", ge=1, le=100)
    total: int = Field(..., description="供应商商品总数", ge=0)
    total_pages: int = Field(..., description="总页数", ge=0)


# endregion

__all__ = ["SupplierProductItemResponse", "SupplierProductListResponse"]
