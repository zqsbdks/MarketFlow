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


# 后续继续添加：
# 1. PurchaseCreateItemRequest：创建进货单中的一条商品明细
# 2. PurchaseCreateRequest：创建进货单
# 3. PurchaseReceiveRequest：签收到货

__all__ = ["PurchasesListRequest"]
