"""商品查询接口的响应模型。"""

from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import ProductStatus


# region 商品列表项
class ProductsItemResponse(BaseModel):
    """商品列表中的单个商品信息。"""

    id: int = Field(..., description="商品ID", ge=1)
    product_no: str = Field(..., description="商品编号", min_length=1, max_length=20)
    name: str = Field(..., description="商品名称", min_length=1, max_length=100)
    # 商品表中的 department_id 和 category_id 都不可为空，所以名称也应必填。
    department_name: str = Field(..., description="所属部门名称")
    category_name: str = Field(..., description="所属分类名称")
    purchase_price: Decimal = Field(..., description="进货价", ge=0)
    sale_price: Decimal = Field(..., description="销售价", ge=0)
    stock_quantity: int = Field(..., description="库存数量", ge=0)
    status: ProductStatus = Field(..., description="商品销售状态")

    model_config = ConfigDict(from_attributes=True)


# endregion


# region 商品列表响应
class ProductsListResponse(BaseModel):
    """商品列表及分页信息。"""

    items: list[ProductsItemResponse] = Field(..., description="商品列表")
    page: int = Field(..., description="当前页码", ge=1)
    page_size: int = Field(..., description="每页数量", ge=1, le=100)
    total: int = Field(..., description="商品总数", ge=0)
    total_pages: int = Field(..., description="总页数", ge=0)

    model_config = ConfigDict(from_attributes=True)


# endregion


# region 商品详情响应
class DepartmentResponse(BaseModel):
    """商品所属部门的简要信息。"""

    id: int = Field(..., description="部门ID", ge=1)
    name: str = Field(..., description="部门名称", min_length=1, max_length=50)

    model_config = ConfigDict(from_attributes=True)


class CategoryResponse(BaseModel):
    """商品所属分类的简要信息。"""

    id: int = Field(..., description="分类ID", ge=1)
    name: str = Field(..., description="分类名称", min_length=1, max_length=50)

    model_config = ConfigDict(from_attributes=True)


class ItemResponse(BaseModel):
    """单个商品的完整详情。"""

    id: int = Field(..., description="商品ID", ge=1)
    product_no: str = Field(..., description="商品编号", min_length=1, max_length=20)
    name: str = Field(..., description="商品名称", min_length=1, max_length=100)
    department: DepartmentResponse = Field(..., description="所属部门信息")
    category: CategoryResponse = Field(..., description="所属分类信息")
    purchase_price: Decimal = Field(..., description="进货价", ge=0)
    sale_price: Decimal = Field(..., description="销售价", ge=0)
    stock_quantity: int = Field(..., description="库存数量", ge=0)
    status: ProductStatus = Field(..., description="商品销售状态")

    model_config = ConfigDict(from_attributes=True)


# endregion


__all__ = [
    "CategoryResponse",
    "DepartmentResponse",
    "ItemResponse",
    "ProductsItemResponse",
    "ProductsListResponse",
]
