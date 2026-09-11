"""供应商商品目录接口的请求模型。"""

from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class SupplierProductsListRequest(BaseModel):
    """供应商商品列表的分页及可选筛选条件。"""

    page: int = Field(1, description="页码", ge=1)
    page_size: int = Field(10, description="每页数量", ge=1, le=100)
    supplier_id: int | None = Field(None, description="供应商ID", ge=1)
    keyword: str | None = Field(None, description="商品名称关键字", min_length=1, max_length=100)
    is_active: bool | None = Field(None, description="是否仍在供应")
    model_config = ConfigDict(str_strip_whitespace=True)


class SupplierProductCreateRequest(BaseModel):
    """店长向供应商商品目录中添加商品时提交的数据。"""

    supplier_id: int = Field(..., description="供应商ID", ge=1)
    name: str = Field(..., description="供应商商品名称", min_length=1, max_length=100)
    unit_cost: Decimal = Field(..., description="当前默认进货单价", ge=0, decimal_places=2)
    shelf_life_days: int | None = Field(None, description="默认保质期天数", ge=1)
    model_config = ConfigDict(str_strip_whitespace=True)


class SupplierProductStatusUpdateRequest(BaseModel):
    """店长启用或停用供应商商品时提交的状态。"""

    is_active: bool = Field(..., description="是否仍在供应")


class SupplierProductUpdateRequest(BaseModel):
    """店长修改供应商商品资料时提交的可选字段。"""

    name: str | None = Field(None, description="供应商商品名称", min_length=1, max_length=100)
    unit_cost: Decimal | None = Field(None, description="当前默认进货单价", ge=0, decimal_places=2)
    shelf_life_days: int | None = Field(None, description="默认保质期天数", ge=1)
    model_config = ConfigDict(str_strip_whitespace=True)


__all__ = [
    "SupplierProductCreateRequest",
    "SupplierProductsListRequest",
    "SupplierProductStatusUpdateRequest",
    "SupplierProductUpdateRequest",
]
