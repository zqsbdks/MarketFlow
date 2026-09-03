"""部门查询接口的响应模型。"""

from pydantic import BaseModel, ConfigDict, Field


# region 部门列表项
class DepartmentItemResponse(BaseModel):
    """部门列表中的单个部门信息。"""

    id: int = Field(..., description="部门ID", ge=1)
    name: str = Field(
        ...,
        description="部门名称",
        min_length=1,
        max_length=50,
    )

    model_config = ConfigDict(from_attributes=True)


# endregion


__all__ = ["DepartmentItemResponse"]
