"""营业报表接口的响应模型。"""

from decimal import Decimal
from typing import Any

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


# region 营业分析响应
class ReportAnalyticsResponse(BaseModel):
    """按请求选择返回营业分析指标；未选择的字段不会出现在响应中。"""

    # 所有单值指标直接放在这里；百分数30.00代表30%，不是0.30。
    # None表示分母为0等情况下无法计算，允许负毛利率和负增长率。
    revenue: Decimal | None = Field(None, description="营业额", ge=0)
    sales_cost: Decimal | None = Field(None, description="销售成本", ge=0)
    gross_profit: Decimal | None = Field(None, description="毛利润")
    sales_quantity: int | None = Field(None, description="累计销售商品数量", ge=0)
    sale_count: int | None = Field(None, description="销售单数量", ge=0)
    average_sale_amount: Decimal | None = Field(
        None,
        description="平均每单金额＝营业额÷销售单数；无销售单时为null",
        ge=0,
    )
    average_sale_quantity: Decimal | None = Field(
        None,
        description="平均每单件数＝销量÷销售单数；无销售单时为null",
        ge=0,
    )
    gross_profit_margin: Decimal | None = Field(
        None,
        description="毛利率（%）＝毛利润÷营业额×100；营业额为0时为null",
    )
    revenue_growth_rate: Decimal | None = Field(
        None,
        description="营业额增长率（%）＝本期与上期营业额之差÷上期营业额×100；上期为0或数据不足时为null",
    )
    gross_profit_growth_rate: Decimal | None = Field(
        None,
        description="毛利润增长率（%）＝本期与上期毛利润之差÷上期毛利润×100；上期小于等于0或数据不足时为null",
    )

    # 一个部门对应一个字典，由Service负责填齐下面说明的字段。
    # 不筛选时返回所有部门，筛选后只返回指定部门；占比分母始终是同期全店营业额。
    department_revenue_share: list[dict[str, Any]] | None = Field(
        None,
        description="部门占比列表：每项包含department_id、department_name、revenue_share（百分数，全店营业额为0时为null）",
        examples=[[{"department_id": 1, "department_name": "精肉部", "revenue_share": "25.00"}]],
    )

    # 一个小时、日、月或年对应一个字典，按时间升序排列。
    # 每项包含起止时间、营业额、销售成本、毛利润、销量、单数、毛利率。
    # 字典不再逐字段校验，Service需保证字段齐全、类型正确及计算口径一致。
    sales_trend: list[dict[str, Any]] | None = Field(
        None,
        description="时间趋势列表：只返回有销售的时间段；每项包含start_time、end_time、revenue、sales_cost、gross_profit、sales_quantity、sale_count、gross_profit_margin",
        examples=[
            [
                {
                    "start_time": "2026-09-06T09:00:00",
                    "end_time": "2026-09-06T10:00:00",
                    "revenue": "1000.00",
                    "sales_cost": "700.00",
                    "gross_profit": "300.00",
                    "sales_quantity": 60,
                    "sale_count": 20,
                    "gross_profit_margin": "30.00",
                }
            ]
        ],
    )


# endregion

__all__ = [
    "DepartmentResponse",
    "RankingItemResponse",
    "RankingsResponse",
    "ReportResponse",
    "ReportAnalyticsResponse",
]
