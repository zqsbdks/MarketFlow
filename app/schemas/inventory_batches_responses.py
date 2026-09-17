"""库存批次接口的响应模型。"""

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import InventoryBatchStatus


# region 库存批次列表项响应模型
class InventoryBatchItemResponse(BaseModel):
    """库存批次列表中用于快速浏览的一条批次信息。"""

    # 库存批次表中的基本信息。
    id: int = Field(..., description="批次ID", ge=1)
    batch_no: str = Field(..., description="批次编号", min_length=1, max_length=30)

    # 列表页用于识别商品及所属部门的常用信息。
    product_no: str = Field(..., description="商品编号", min_length=1, max_length=20)
    product_name: str = Field(..., description="商品名称", min_length=1, max_length=100)
    department_name: str = Field(..., description="所属部门名称", min_length=1, max_length=50)

    # 库存数量、保质期和批次处理状态。
    initial_quantity: int = Field(..., description="到货初始数量", ge=1)
    remaining_quantity: int = Field(..., description="当前剩余数量", ge=0)
    production_date: date | None = Field(None, description="生产日期")
    expiration_date: date | None = Field(None, description="到期日期")
    status: InventoryBatchStatus = Field(..., description="批次状态")
    arrived_at: datetime = Field(..., description="到货入库时间")

    # 允许后续直接从具有同名属性的 ORM 对象读取字段。
    # product_name 等平铺字段仍需要在 Service 中手动组装。
    model_config = ConfigDict(from_attributes=True)


# endregion


# region 库存批次分页列表响应模型
class InventoryBatchListResponse(BaseModel):
    """库存批次列表及分页统计信息。"""

    # items 保存当前页实际查询到的库存批次。
    items: list[InventoryBatchItemResponse] = Field(..., description="库存批次列表")
    # page 和 page_size 分别表示当前页码以及每页最大数量。
    page: int = Field(..., description="当前页码", ge=1)
    page_size: int = Field(..., description="每页数量", ge=1, le=100)
    # total 是符合筛选条件的总记录数，不只是当前页的记录数。
    total: int = Field(..., description="库存批次总数", ge=0)
    # total_pages 根据 total 和 page_size 计算，用于前端生成分页按钮。
    total_pages: int = Field(..., description="总页数", ge=0)


# endregion


# region 库存批次详情响应模型
class InventoryBatchDetailResponse(InventoryBatchItemResponse):
    """单个库存批次的完整详情响应。"""

    # 正式商品以及商品所属部门、分类的完整标识信息。
    product_id: int = Field(..., description="商品ID", ge=1)
    department_id: int = Field(..., description="所属部门ID", ge=1)
    category_id: int = Field(..., description="所属分类ID", ge=1)
    category_name: str = Field(..., description="所属分类名称", min_length=1, max_length=50)

    # 来源进货明细和进货单中的历史快照信息。
    supplier_name: str = Field(
        ...,
        description="进货时的供应商名称",
        min_length=1,
        max_length=100,
    )
    purchase_no: str = Field(..., description="来源进货单号", min_length=1, max_length=30)
    purchase_item_id: int = Field(..., description="来源进货明细ID", ge=1)
    unit_cost: Decimal = Field(..., description="本批次进货单价", ge=0, decimal_places=2)

    # 库存批次记录本身的创建和最后更新时间。
    created_at: datetime = Field(..., description="创建时间")
    updated_at: datetime = Field(..., description="更新时间")


# endregion


__all__ = [
    "InventoryBatchDetailResponse",
    "InventoryBatchItemResponse",
    "InventoryBatchListResponse",
]
