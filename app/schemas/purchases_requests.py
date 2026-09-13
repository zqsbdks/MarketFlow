"""进货管理接口的请求模型。"""

from datetime import date

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import PurchaseStatus


# region 获取进货单列表请求
class PurchasesListRequest(BaseModel):
    """进货单列表的分页及可选筛选条件。"""

    page: int = Field(1, description="页码", ge=1)
    page_size: int = Field(10, description="每页数量", ge=1, le=100)
    purchase_no: str | None = Field(
        None,
        description="进货单号，支持完整或部分单号查询",
        min_length=1,
        max_length=30,
    )
    department_id: int | None = Field(None, description="进货所属部门ID", ge=1)
    ordered_at: date | None = Field(
        None,
        description="下单日期，不传则不限制日期",
    )
    arrived_at: date | None = Field(
        None,
        description="实际到货日期，不传则不限制日期",
    )
    status: PurchaseStatus | None = Field(
        None,
        description="进货单状态：pending待到货，arrived已到货",
    )

    # 自动删除进货单号首尾的空格。
    model_config = ConfigDict(str_strip_whitespace=True)


# endregion


# region 创建进货单请求
class CreatePurchaseItemRequest(BaseModel):
    """创建进货单时提交的一条商品明细。"""

    supplier_product_id: int = Field(..., description="供应商商品目录ID", ge=1)
    quantity: int = Field(..., description="进货数量", ge=1)
    production_date: date | None = Field(
        None,
        description="生产日期；不传时使用预计到货日期",
    )
    expiration_date: date | None = Field(
        None,
        description="到期日期；不传时使用生产日期加默认保质期计算",
    )


class CreatePurchaseRequest(BaseModel):
    """创建进货单的请求。"""

    department_id: int = Field(..., description="进货所属部门ID", ge=1)
    items: list[CreatePurchaseItemRequest] = Field(
        ...,
        description="进货商品明细，至少包含一项",
        min_length=1,
    )


# endregion

# 后续签收接口再添加PurchaseReceiveRequest。

__all__ = ["CreatePurchaseItemRequest", "CreatePurchaseRequest", "PurchasesListRequest"]
