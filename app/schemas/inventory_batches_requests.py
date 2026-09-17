"""库存批次接口的请求模型。"""

from pydantic import BaseModel, Field

from app.models.enums import InventoryBatchStatus


# region 库存批次列表请求模型
class InventoryBatchListRequest(BaseModel):
    """库存批次列表的分页参数和可选状态筛选条件。"""

    page: int = Field(1, ge=1, description="当前页码")
    page_size: int = Field(10, ge=1, le=100, description="每页数量")
    status: InventoryBatchStatus | None = Field(
        None,
        description="批次状态；不传时查询全部部门的所有状态批次",
    )


# endregion


__all__ = ["InventoryBatchListRequest"]
