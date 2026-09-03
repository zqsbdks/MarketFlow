"""商品分类查询接口的请求模型。"""

from pydantic import BaseModel, Field


# region 商品分类列表查询参数
class CategoryListRequest(BaseModel):
    """商品分类列表的可选筛选条件。"""

    department_id: int | None = Field(
        None,
        description="按部门ID筛选分类",
        ge=1,
    )


# endregion


__all__ = ["CategoryListRequest"]
