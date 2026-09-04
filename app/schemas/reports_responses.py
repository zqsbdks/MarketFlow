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


# region 部门销售对比响应
class DepartmentResponse(BaseModel):
    """单个部门的营业对比数据。"""

    department_id: int = Field(..., description="部门ID", ge=1)
    department_name: str = Field(..., description="部门名称", min_length=1, max_length=50)
    revenue: Decimal = Field(..., description="部门营收", ge=0)
    gross_profit: Decimal = Field(..., description="部门毛利")
    sales_quantity: int = Field(..., description="部门销售数量", ge=0)

    model_config = ConfigDict(from_attributes=True)


# endregion


# region 销售排行响应
class RankingItemResponse(BaseModel):
    """销售排行中的一个商品或商品分类。"""

    rank: int = Field(..., description="当前排序名次", ge=1)
    id: int = Field(..., description="商品ID或商品分类ID", ge=1)
    name: str = Field(..., description="商品名称或商品分类名称", min_length=1)
    quantity: int = Field(..., description="累计销售数量", ge=0)
    amount: Decimal = Field(..., description="累计销售金额", ge=0)

    model_config = ConfigDict(from_attributes=True)


class RankingsResponse(BaseModel):
    """销售排行列表及分页信息。"""

    items: list[RankingItemResponse] = Field(..., description="销售排行列表")
    page: int = Field(..., description="当前页码", ge=1)
    page_size: int = Field(..., description="每页数量", ge=1, le=100)
    total: int = Field(..., description="参与排行的商品或分类总数", ge=0)
    total_pages: int = Field(..., description="总页数", ge=0)

    model_config = ConfigDict(from_attributes=True)


# endregion


__all__ = [
    "DepartmentResponse",
    "RankingItemResponse",
    "RankingsResponse",
    "ReportResponse",
]
