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


class DepartmentResponse(BaseModel):
    """单个部门的营业对比数据。"""

    department_id: int = Field(..., description="部门ID", ge=1)
    department_name: str = Field(..., description="部门名称", min_length=1, max_length=50)
    revenue: Decimal = Field(..., description="部门营收", ge=0)
    gross_profit: Decimal = Field(..., description="部门毛利")
    sales_quantity: int = Field(..., description="部门销售数量", ge=0)

    model_config = ConfigDict(from_attributes=True)


__all__ = ["DepartmentResponse", "ReportResponse"]
