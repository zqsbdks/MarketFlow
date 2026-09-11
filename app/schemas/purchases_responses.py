"""进货管理接口的响应模型。"""

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import PurchaseStatus


# region 进货单列表项
class PurchaseListItemResponse(BaseModel):
    """进货单列表中的一张进货单。"""

    id: int = Field(..., description="进货单ID", ge=1)
    purchase_no: str = Field(..., description="进货单号", min_length=1, max_length=30)
    department_id: int = Field(..., description="进货所属部门ID", ge=1)
    department_name: str = Field(..., description="进货所属部门名称", min_length=1, max_length=50)

    # created_by和received_by在数据库中保存的都是员工ID。
    created_by: int = Field(..., description="创建进货单的员工ID", ge=1)
    created_by_name: str = Field(
        ..., description="创建进货单的员工姓名", min_length=1, max_length=20
    )
    received_by: int | None = Field(None, description="签收员工ID", ge=1)
    received_by_name: str | None = Field(None, description="签收员工姓名", max_length=20)

    ordered_at: datetime = Field(..., description="下单时间")
    expected_arrival_at: datetime = Field(..., description="预计到货时间")
    arrived_at: datetime | None = Field(None, description="实际到货时间")
    total_amount: Decimal = Field(..., description="进货总金额", ge=0, decimal_places=2)
    status: PurchaseStatus = Field(..., description="进货单状态")

    # item_count统计进货明细行数，total_quantity统计所有明细的进货数量之和。
    item_count: int = Field(..., description="商品种类数", ge=0)
    total_quantity: int = Field(..., description="进货商品总数量", ge=0)
    created_at: datetime = Field(..., description="记录创建时间")
    updated_at: datetime = Field(..., description="记录更新时间")

    # 允许模型读取SQLAlchemy对象的同名属性；名称和统计字段仍由Service组装。
    model_config = ConfigDict(from_attributes=True)


# endregion


# region 进货单详情
class PurchaseItemResponse(BaseModel):
    """进货单详情中的一条商品明细。"""

    id: int = Field(..., description="进货明细ID", ge=1)
    supplier_product_id: int = Field(..., description="供应商商品目录ID", ge=1)
    product_id: int | None = Field(None, description="签收后生成或匹配的正式商品ID", ge=1)
    supplier_id: int = Field(..., description="供应商ID", ge=1)
    product_no: str | None = Field(None, description="下单时商品编号快照", max_length=20)
    product_name: str = Field(..., description="下单时商品名称", min_length=1, max_length=100)
    supplier_name: str = Field(..., description="下单时供应商名称", min_length=1, max_length=100)
    quantity: int = Field(..., description="进货数量", ge=1)
    unit_cost: Decimal = Field(..., description="本次进货单价", ge=0, decimal_places=2)
    subtotal: Decimal = Field(..., description="进货金额小计", ge=0, decimal_places=2)
    production_date: date | None = Field(None, description="生产日期")
    expiration_date: date | None = Field(None, description="到期日期")


class PurchaseDetailResponse(PurchaseListItemResponse):
    """进货单汇总信息及其全部商品明细。"""

    items: list[PurchaseItemResponse] = Field(..., description="进货商品明细")


# endregion


# region 进货单列表响应
class PurchaseListResponse(BaseModel):
    """进货单列表及分页信息。"""

    items: list[PurchaseListItemResponse] = Field(..., description="进货单列表")
    page: int = Field(..., description="当前页码", ge=1)
    page_size: int = Field(..., description="每页数量", ge=1, le=100)
    total: int = Field(..., description="进货单总数", ge=0)
    total_pages: int = Field(..., description="总页数", ge=0)


# endregion


__all__ = [
    "PurchaseDetailResponse",
    "PurchaseItemResponse",
    "PurchaseListItemResponse",
    "PurchaseListResponse",
]
