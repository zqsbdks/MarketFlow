"""销售记录接口的请求模型。"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


# region 销售单列表查询参数
class SalesListRequest(BaseModel):
    """销售单列表的分页参数及可选筛选条件。"""

    page: int = Field(1, description="当前页码", ge=1)
    page_size: int = Field(10, description="每页数量", ge=1, le=100)
    start_time: datetime | None = Field(
        None,
        description="开始时间，允许范围为每天09:00至21:00",
    )
    end_time: datetime | None = Field(
        None,
        description="结束时间，允许范围为每天09:00至21:00",
    )
    sale_no: str | None = Field(
        None,
        description="销售单号",
        min_length=1,
        max_length=30,
    )

    model_config = ConfigDict(str_strip_whitespace=True)


# endregion


# region 创建销售单请求模型
class CreateSaleItemRequest(BaseModel):
    """收银台扫描的一种商品及购买数量。"""

    # product_id 对应扫码后解析出的正式商品主键。
    product_id: int = Field(..., description="商品ID", ge=1)
    # quantity 是顾客购买该商品的件数，至少为1。
    quantity: int = Field(..., description="购买数量", ge=1)


class CreateSaleRequest(BaseModel):
    """收银台完成结账时提交的商品列表。"""

    # 一张销售单至少需要一个商品；同一商品重复出现时由 Service 自动合并数量。
    items: list[CreateSaleItemRequest] = Field(..., description="销售商品", min_length=1)


# endregion


__all__ = ["CreateSaleItemRequest", "CreateSaleRequest", "SalesListRequest"]
