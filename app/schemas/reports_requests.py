"""营业报表接口的请求模型。"""

from datetime import datetime

from pydantic import BaseModel, Field


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


__all__ = ["DepartmentRequest", "ReportRequest"]
