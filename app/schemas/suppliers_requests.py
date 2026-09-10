"""供应商管理接口的请求模型。"""

from pydantic import BaseModel, Field


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

__all__ = ["SuppliersListRequest", "SuppliersStatusUpdateRequest"]
