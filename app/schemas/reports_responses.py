"""营业报表接口的响应模型。"""

from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


# region 营业概览响应
class ReportResponse(BaseModel):
    """整个店铺或指定部门的营业汇总数据。"""

    revenue: Decimal = Field(..., description="营业总额", ge=0)
    sales_cost: Decimal = Field(..., description="销售成本", ge=0)
    gross_profit: Decimal = Field(..., description="毛利润")
    sales_quantity: int = Field(..., description="销售商品总数量", ge=0)
    sale_count: int = Field(..., description="销售单数量", ge=0)

    model_config = ConfigDict(from_attributes=True)


# endregion


__all__ = ["ReportResponse"]
