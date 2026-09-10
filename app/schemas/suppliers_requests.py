"""供应商管理接口的请求模型。"""

from pydantic import BaseModel, ConfigDict, Field


# region 供应商列表查询参数
class SuppliersListRequest(BaseModel):
    """供应商列表的分页及可选状态筛选条件。"""

    page: int = Field(1, description="页码", ge=1)
    page_size: int = Field(10, description="每页数量", ge=1, le=100)
    is_active: bool | None = Field(None, description="是否启用")


# endregion


# region 修改供应商状态请求
class SuppliersStatusUpdateRequest(BaseModel):
    """店长启用或停用供应商时提交的状态。"""

    # 使用...表示前端必须明确传入true或false，避免遗漏后默认为启用。
    is_active: bool = Field(..., description="是否继续合作")


# endregion


# region 修改供应商详情请求
class SuppliersUpdateRequest(BaseModel):
    """店长修改供应商资料时提交的可选字段。"""

    # 默认值为None表示字段可以不传；Service使用exclude_unset=True只更新实际传入的字段。
    name: str | None = Field(None, description="供应商名称", min_length=1, max_length=100)
    contact_name: str | None = Field(None, description="联系人姓名", min_length=1, max_length=50)
    phone: str | None = Field(None, description="联系电话", min_length=1, max_length=30)
    address: str | None = Field(None, description="供应商地址", min_length=1, max_length=255)

    # 自动去掉字符串首尾的空格，例如把"  某供应商  "处理为"某供应商"。
    model_config = ConfigDict(str_strip_whitespace=True)


# endregion


__all__ = ["SuppliersListRequest", "SuppliersStatusUpdateRequest", "SuppliersUpdateRequest"]
