"""供应商管理接口的响应模型。"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


# region 供应商列表项
class SupplierItemResponse(BaseModel):
    """供应商列表中的单个供应商。"""

    id: int = Field(..., description="供应商ID", ge=1)
    supplier_no: str = Field(
        ...,
        description="供应商编号",
        min_length=1,
        max_length=20,
    )
    name: str = Field(
        ...,
        description="供应商名称",
        min_length=1,
        max_length=100,
    )
    # 数据库允许以下三项为空，因此响应模型也必须允许返回null。
    contact_name: str | None = Field(None, description="联系人姓名", max_length=50)
    phone: str | None = Field(None, description="联系电话", max_length=30)
    address: str | None = Field(None, description="地址", max_length=255)
    is_active: bool = Field(..., description="是否继续合作")
    created_at: datetime = Field(..., description="创建时间")
    updated_at: datetime = Field(..., description="更新时间")

    model_config = ConfigDict(from_attributes=True)


# endregion


# region 供应商列表响应
class SupplierListResponse(BaseModel):
    """供应商列表及分页信息。"""

    items: list[SupplierItemResponse] = Field(..., description="供应商列表")
    page: int = Field(..., description="当前页码", ge=1)
    page_size: int = Field(..., description="每页数量", ge=1, le=100)
    total: int = Field(..., description="供应商总数", ge=0)
    total_pages: int = Field(..., description="总页数", ge=0)

    model_config = ConfigDict(from_attributes=True)


# endregion

__all__ = ["SupplierItemResponse", "SupplierListResponse"]
