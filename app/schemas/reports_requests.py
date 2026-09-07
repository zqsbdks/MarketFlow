"""营业报表接口的请求模型。"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import RankingGroupBy, RankingSortBy, RankingSortOrder, ReportMetric


# region 营业概览查询参数
class ReportRequest(BaseModel):
    """营业概览的可选时间范围和部门筛选条件。"""

    start_time: datetime | None = Field(
        None,
        description="开始时间，允许范围为每天 09:00 至 21:00",
    )
    end_time: datetime | None = Field(
        None,
        description="结束时间，允许范围为每天 09:00 至 21:00",
    )
    department_id: int | None = Field(
        None,
        description="所属部门ID，不传时统计整个店铺",
        ge=1,
    )


# endregion


# region 部门销售对比查询参数
class DepartmentRequest(BaseModel):
    """部门营业对比的可选时间范围。"""

    start_time: datetime | None = Field(
        None,
        description="开始时间，允许范围为每天 09:00 至 21:00",
    )
    end_time: datetime | None = Field(
        None,
        description="结束时间，允许范围为每天 09:00 至 21:00",
    )


# endregion


# region 销售排行查询参数
class RankingsRequest(BaseModel):
    """销售排行的筛选、汇总、排序和分页参数。"""

    start_date: datetime | None = Field(
        None,
        description="开始日期时间，允许范围为每天 09:00 至 21:00",
    )
    end_date: datetime | None = Field(
        None,
        description="结束日期时间，允许范围为每天 09:00 至 21:00",
    )
    department_id: int | None = Field(
        None,
        description="部门ID，不传时统计整个店铺",
        ge=1,
    )
    category_id: int | None = Field(
        None,
        description="商品分类ID，不传时统计全部分类",
        ge=1,
    )
    group_by: RankingGroupBy = Field(
        RankingGroupBy.PRODUCT,
        description="汇总方式：product按商品，category按分类",
    )
    sort_by: RankingSortBy = Field(
        RankingSortBy.QUANTITY,
        description="排序指标：quantity销售数量，amount销售金额",
    )
    sort_order: RankingSortOrder = Field(
        RankingSortOrder.DESC,
        description="排序方向：asc升序，desc降序",
    )
    page: int = Field(1, description="当前页码", ge=1)
    page_size: int = Field(10, description="每页数量", ge=1, le=100)

    model_config = ConfigDict(str_strip_whitespace=True)


# endregion


# region 营业分析查询参数
class ReportAnalyticsRequest(BaseModel):
    """统一营业分析的时间范围、部门筛选和趋势粒度。"""

    # 需要明确本期范围，才能计算紧邻本期之前的上一等长周期。
    # 时间先后和营业时段校验由 Service 处理；查询包含开始、不包含结束。
    start_time: datetime = Field(
        ...,
        description="开始时间（包含），门店当地时间，每天09:00至21:00",
    )
    end_time: datetime = Field(
        ...,
        description="结束时间（不包含），须晚于开始时间，每天09:00至21:00",
    )
    department_id: int | None = Field(
        None,
        description="部门ID；不传统计全店，传入则统计该部门，占比分母仍为同期全店营业额",
        ge=1,
    )
    interval: Literal["hour", "day", "month", "year"] = Field(
        "day",
        description="营业趋势分组：hour按小时、day按日、month按月、year按年",
    )
    metrics: list[ReportMetric] = Field(
        ...,
        min_length=1,
        description="需要返回的指标，可重复传入metrics选择多项",
    )


# endregion

__all__ = [
    "DepartmentRequest",
    "RankingGroupBy",
    "RankingSortBy",
    "RankingSortOrder",
    "RankingsRequest",
    "ReportRequest",
    "ReportAnalyticsRequest",
    "ReportMetric",
]
