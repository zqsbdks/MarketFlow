"""商品查询及修改接口的请求模型。"""

from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

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


# region 修改商品状态请求模型
class ProductStatusUpdateRequest(BaseModel):
    """店长或正式员工修改商品销售状态时提交的数据。"""

    # ProductStatus 只允许 on_sale（上架）和 stopped（停售）两个枚举值。
    status: ProductStatus = Field(
        ...,
        description="商品销售状态：on_sale为上架，stopped为停售",
    )


# endregion


# region 修改商品请求模型
class UpdateProductRequest(BaseModel):
    """店长或正式员工修改商品资料时提交的可选字段。"""

    # 所有字段都是可选字段：前端只传需要修改的字段即可。
    # Service 层使用 model_dump(exclude_unset=True) 后，未传字段不会覆盖数据库原值。
    # name：商品在查询、销售等页面显示的名称。
    name: str | None = Field(
        None,
        description="商品名称",
        min_length=1,
        max_length=100,
    )
    # category_id：商品准备修改到的分类 ID，Service 会检查分类及所属部门。
    category_id: int | None = Field(
        None,
        description="商品分类ID",
        ge=1,
    )
    # sale_price：商品对外销售价格；进货价格不允许通过本接口修改。
    sale_price: Decimal | None = Field(
        None,
        description="销售价格",
        ge=0,
        decimal_places=2,
    )
    # expiry_warning_days：距离到期多少天时开始显示临期提醒，传 null 可取消提醒。
    expiry_warning_days: int | None = Field(
        None,
        description="临期提前提醒天数；例如填写1，表示到期前1天开始提醒",
        ge=0,
    )

    # 自动去除字符串首尾空格，避免把“ 牛肉 ”保存为带空格的商品名称。
    model_config = ConfigDict(str_strip_whitespace=True)


# endregion


__all__ = [
    "ProductStatusUpdateRequest",
    "ProductsListRequest",
    "UpdateProductRequest",
]
