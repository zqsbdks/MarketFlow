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


__all__ = ["SalesListRequest"]
