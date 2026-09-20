"""库存批次接口的请求模型。"""

from datetime import date

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import InventoryBatchStatus


# region 库存批次列表请求模型
class InventoryBatchListRequest(BaseModel):
    """库存批次列表的分页参数和可选状态筛选条件。"""

    page: int = Field(1, ge=1, description="当前页码")
    page_size: int = Field(10, ge=1, le=100, description="每页数量")
    status: InventoryBatchStatus | None = Field(
        None,
        description="批次状态；不传时查询全部部门的所有状态批次",
    )
    supplier_id: int | None = Field(None, description="供应商ID", ge=1)
    product_id: int | None = Field(None, description="商品ID", ge=1)
    department_id: int | None = Field(None, description="所属部门ID", ge=1)
    expiration_start: date | None = Field(None, description="最早到期日期")
    expiration_end: date | None = Field(None, description="最晚到期日期")


# endregion


# region 修改库存批次数量请求模型
class InventoryBatchQuantityUpdateRequest(BaseModel):
    """人工盘点后修改某个批次剩余库存时提交的数据。"""

    remaining_quantity: int = Field(..., ge=0, description="修改后的批次剩余数量")
    reason: str | None = Field(
        None,
        min_length=1,
        max_length=255,
        description="修改原因，可不填写",
    )

    model_config = ConfigDict(str_strip_whitespace=True)


# endregion


# region 废弃过期批次请求模型
class InventoryBatchDiscardRequest(BaseModel):
    """确认下架并废弃某个过期批次时提交的可选说明。"""

    reason: str | None = Field(
        None,
        min_length=1,
        max_length=255,
        description="废弃原因，可不填写；未填写时由后端使用默认原因",
    )

    model_config = ConfigDict(str_strip_whitespace=True)


# endregion


__all__ = [
    "InventoryBatchDiscardRequest",
    "InventoryBatchListRequest",
    "InventoryBatchQuantityUpdateRequest",
]
