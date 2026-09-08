"""供应商管理 API 路由。"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies.auth import get_current_employee_id
from app.dependencies.db import get_db
from app.schemas.base import ResponseModel
from app.schemas.suppliers_requests import SuppliersListRequest
from app.schemas.suppliers_responses import SupplierListResponse
from app.services.suppliers import get_suppliers_list_service

suppliers_router = APIRouter(prefix="/suppliers", tags=["suppliers"])


# region 获取供应商列表接口
@suppliers_router.get(
    "/list",
    response_model=ResponseModel[SupplierListResponse],
    summary="获取供应商列表",
    description="店长分页获取供应商列表，并可按照启用状态筛选。",
)
async def get_suppliers_list(
    db: AsyncSession = Depends(get_db),
    current_employee_id: int = Depends(get_current_employee_id),
    request: SuppliersListRequest = Depends(),
) -> ResponseModel[SupplierListResponse]:
    """接收分页和状态参数，并使用统一响应格式返回供应商列表。"""

    suppliers = await get_suppliers_list_service(
        page=request.page,
        page_size=request.page_size,
        is_active=request.is_active,
        current_employee_id=current_employee_id,
        db=db,
    )

    return ResponseModel[SupplierListResponse](
        message="获取供应商列表成功",
        data=suppliers,
    )


# endregion

__all__ = ["suppliers_router"]
