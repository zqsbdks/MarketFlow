"""商品查询接口的请求模型。"""

from pydantic import BaseModel, Field

from app.models.enums import ProductStatus


# region 商品列表查询参数
class ProductsListRequest(BaseModel):
    """商品列表的分页参数及可选筛选条件。"""

    page: int = Field(1, description="当前页码", ge=1)
    page_size: int = Field(10, description="每页数量", ge=1, le=100)
    keyword: str | None = Field(
        None,
        description="商品名称关键字",
        min_length=1,
        max_length=100,
    )
    department_id: int | None = Field(None, description="所属部门ID", ge=1)
    category_id: int | None = Field(None, description="所属分类ID", ge=1)
    status: ProductStatus | None = Field(None, description="商品销售状态")


# endregion


__all__ = ["ProductsListRequest"]
