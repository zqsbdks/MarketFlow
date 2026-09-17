"""库存批次 API 路由。"""

from fastapi import APIRouter, Body, Depends, Path
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies.auth import get_current_employee_id
from app.dependencies.db import get_db
from app.schemas.base import ResponseModel
from app.schemas.inventory_batches_requests import (
    InventoryBatchListRequest,
    InventoryBatchQuantityUpdateRequest,
)
from app.schemas.inventory_batches_responses import (
    InventoryBatchDetailResponse,
    InventoryBatchListResponse,
)
from app.services.inventory_batches import (
    get_inventory_batch_detail_service,
    get_inventory_batches_list_service,
    update_inventory_batch_quantity_service,
)

# 最终接口地址统一以 /api/v1/inventory-batches 开头。
inventory_batches_router = APIRouter(
    prefix="/inventory-batches",
    tags=["inventory-batches"],
)


# region 获取库存批次列表
@inventory_batches_router.get(
    "/list",
    response_model=ResponseModel[InventoryBatchListResponse],
    summary="获取库存批次列表",
    description="所有账号状态正常的员工均可分页查看全部部门的库存批次。",
)
async def get_inventory_batches_list(
    # request 接收页码、每页数量和可选批次状态查询参数。
    request: InventoryBatchListRequest = Depends(),
    # current_employee_id 用于检查员工存在、账号启用且已经修改初始密码。
    current_employee_id: int = Depends(get_current_employee_id),
    # db 是当前请求使用的异步数据库会话。
    db: AsyncSession = Depends(get_db),
) -> ResponseModel[InventoryBatchListResponse]:
    """校验当前员工账号，并返回全部部门的分页库存批次列表。"""

    batches = await get_inventory_batches_list_service(
        page=request.page,
        page_size=request.page_size,
        status=request.status,
        supplier_id=request.supplier_id,
        product_id=request.product_id,
        department_id=request.department_id,
        expiration_start=request.expiration_start,
        expiration_end=request.expiration_end,
        current_employee_id=current_employee_id,
        db=db,
    )

    return ResponseModel[InventoryBatchListResponse](
        message="库存批次列表获取成功",
        data=batches,
    )


# endregion


# region 修改库存批次数量
@inventory_batches_router.put(
    "/{batch_id}/quantity",
    response_model=ResponseModel[InventoryBatchDetailResponse],
    summary="修改库存批次数量",
    description="店长可修改全部批次，正式员工只能修改本部门批次，并同步商品总库存。",
)
async def update_inventory_batch_quantity(
    batch_id: int = Path(..., description="库存批次ID", ge=1),
    request: InventoryBatchQuantityUpdateRequest = Body(...),
    current_employee_id: int = Depends(get_current_employee_id),
    db: AsyncSession = Depends(get_db),
) -> ResponseModel[InventoryBatchDetailResponse]:
    """接收新的批次剩余数量和可选理由，返回修改后的批次详情。"""

    batch = await update_inventory_batch_quantity_service(
        batch_id=batch_id,
        request=request,
        current_employee_id=current_employee_id,
        db=db,
    )
    return ResponseModel[InventoryBatchDetailResponse](
        message="库存批次数量修改成功",
        data=batch,
    )


# endregion


# region 获取库存批次详情
@inventory_batches_router.get(
    "/{batch_id}",
    response_model=ResponseModel[InventoryBatchDetailResponse],
    summary="获取库存批次详情",
    description="所有账号状态正常的员工均可查看指定库存批次的完整详情。",
)
async def get_inventory_batch_detail(
    # batch_id 来自 URL 路径，例如 /inventory-batches/12 中的 12。
    batch_id: int = Path(..., description="库存批次ID", ge=1),
    # current_employee_id 用于检查员工存在、账号启用且已经修改初始密码。
    current_employee_id: int = Depends(get_current_employee_id),
    # db 是当前请求使用的异步数据库会话。
    db: AsyncSession = Depends(get_db),
) -> ResponseModel[InventoryBatchDetailResponse]:
    """校验当前员工账号，并返回指定库存批次的完整详情。"""

    batch = await get_inventory_batch_detail_service(
        batch_id=batch_id,
        current_employee_id=current_employee_id,
        db=db,
    )

    return ResponseModel[InventoryBatchDetailResponse](
        message="库存批次详情获取成功",
        data=batch,
    )


# endregion


__all__ = ["inventory_batches_router"]
