"""商品分类查询接口的响应模型。"""

from pydantic import BaseModel, ConfigDict, Field


# region 商品分类列表项
class CategoriesItemResponse(BaseModel):
    """商品分类列表中的单个分类信息。"""

    id: int = Field(..., description="分类ID", ge=1)
    name: str = Field(
        ...,
        description="分类名称",
        min_length=1,
        max_length=50,
    )
    department_id: int = Field(..., description="所属部门ID", ge=1)

    model_config = ConfigDict(from_attributes=True)


# endregion


__all__ = ["CategoriesItemResponse"]
