"""营业报表接口的请求模型。"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import RankingGroupBy, RankingSortBy, RankingSortOrder


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


__all__ = [
    "DepartmentRequest",
    "RankingGroupBy",
    "RankingSortBy",
    "RankingSortOrder",
    "RankingsRequest",
    "ReportRequest",
]
