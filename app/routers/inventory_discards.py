"""商品废弃 API。"""

from fastapi import APIRouter, Depends, Path
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies.auth import get_current_employee_id
from app.dependencies.db import get_db
from app.schemas.base import ResponseModel
from app.schemas.inventory_discards import (
    DiscardCreateRequest,
    DiscardListRequest,
    DiscardListResponse,
    DiscardPlanRequest,
    DiscardPlanResponse,
    DiscardResponse,
    DiscardStockResponse,
)
from app.services.inventory_discards import (
    create_discard,
    get_discard_stock,
    list_discards,
    preview_discard,
)

inventory_discards_router = APIRouter(prefix="/inventory-discards", tags=["inventory-discards"])


@inventory_discards_router.get("/list", response_model=ResponseModel[DiscardListResponse])
async def get_list(
    request: DiscardListRequest = Depends(),
    employee_id: int = Depends(get_current_employee_id),
    db: AsyncSession = Depends(get_db),
):
    return ResponseModel(data=await list_discards(request, employee_id, db))


@inventory_discards_router.get(
    "/products/{product_id}/stock", response_model=ResponseModel[DiscardStockResponse]
)
async def get_stock(
    product_id: int = Path(ge=1),
    employee_id: int = Depends(get_current_employee_id),
    db: AsyncSession = Depends(get_db),
):
    return ResponseModel(data=await get_discard_stock(product_id, employee_id, db))


@inventory_discards_router.post("/preview", response_model=ResponseModel[DiscardPlanResponse])
async def preview(
    request: DiscardPlanRequest,
    employee_id: int = Depends(get_current_employee_id),
    db: AsyncSession = Depends(get_db),
):
    return ResponseModel(data=await preview_discard(request, employee_id, db))


@inventory_discards_router.post("", response_model=ResponseModel[DiscardResponse])
async def create(
    request: DiscardCreateRequest,
    employee_id: int = Depends(get_current_employee_id),
    db: AsyncSession = Depends(get_db),
):
    return ResponseModel(
        message="商品废弃完成，库存已同步扣减", data=await create_discard(request, employee_id, db)
    )
