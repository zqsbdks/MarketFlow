"""供应商管理 API 路由。"""

from fastapi import APIRouter, Depends, Path
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies.auth import get_current_employee_id
from app.dependencies.db import get_db
from app.schemas.base import ResponseModel
from app.schemas.suppliers_requests import (
    SuppliersCreateRequest,
    SuppliersListRequest,
    SuppliersStatusUpdateRequest,
    SuppliersUpdateRequest,
)
from app.schemas.suppliers_responses import SupplierItemResponse, SupplierListResponse
from app.services.suppliers import (
    create_supplier_service,
    get_supplier_detail_service,
    get_suppliers_list_service,
    update_supplier_service,
    update_supplier_status_service,
)

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


# region 获取供应商详情接口
@suppliers_router.get(
    "/{supplier_id}",
    response_model=ResponseModel[SupplierItemResponse],
    summary="获取供应商详情",
    description="获取供应商详情。",
)
async def get_supplier_detail(
    supplier_id: int = Path(..., description="供应商ID", ge=1),
    db: AsyncSession = Depends(get_db),
    current_employee_id: int = Depends(get_current_employee_id),
) -> ResponseModel[SupplierItemResponse]:
    """接收供应商ID，并使用统一响应格式返回供应商详情。"""

    supplier = await get_supplier_detail_service(
        supplier_id=supplier_id,
        current_employee_id=current_employee_id,
        db=db,
    )

    return ResponseModel[SupplierItemResponse](
        message="获取供应商详情成功",
        data=supplier,
    )


# endregion


# region 修改供应商启用状态接口
@suppliers_router.put(
    "/{supplier_id}/status",
    response_model=ResponseModel[SupplierItemResponse],
    summary="修改供应商启用状态",
    description="店长修改供应商启用状态。",
)
async def update_supplier_status(
    status: SuppliersStatusUpdateRequest,
    supplier_id: int = Path(..., description="供应商ID", ge=1),
    current_employee_id: int = Depends(get_current_employee_id),
    db: AsyncSession = Depends(get_db),
) -> ResponseModel[SupplierItemResponse]:
    """接收供应商ID和启用状态参数，并使用统一响应格式返回修改后的供应商信息。"""

    supplier = await update_supplier_status_service(
        supplier_id=supplier_id,
        is_active=status.is_active,  # 请求体中明确提交的新合作状态。
        current_employee_id=current_employee_id,
        db=db,
    )

    return ResponseModel[SupplierItemResponse](
        message="修改供应商启用状态成功",
        data=supplier,
    )


# endregion

# region 修改供应商详情接口


@suppliers_router.put(
    "/{supplier_id}",
    response_model=ResponseModel[SupplierItemResponse],
    summary="修改供应商详情",
    description="店长修改供应商详情。",
)
async def update_supplier_details(
    request: SuppliersUpdateRequest,
    supplier_id: int = Path(..., description="供应商ID", ge=1),
    current_employee_id: int = Depends(get_current_employee_id),
    db: AsyncSession = Depends(get_db),
) -> ResponseModel[SupplierItemResponse]:
    """接收供应商ID和修改后的供应商信息，并使用统一响应格式返回修改后的供应商信息。"""

    # request是前端提交的修改内容；Service负责权限、数据和重复值校验。
    updated_supplier = await update_supplier_service(
        supplier_id=supplier_id,
        request=request,
        current_employee_id=current_employee_id,
        db=db,
    )

    return ResponseModel[SupplierItemResponse](
        message="修改供应商详情成功",
        data=updated_supplier,
    )


# endregion

# region 创建供应商接口


@suppliers_router.post(
    "/",
    response_model=ResponseModel[SupplierItemResponse],
    summary="创建供应商",
    description="店长创建供应商。",
)
async def create_supplier(
    request: SuppliersCreateRequest,
    current_employee_id: int = Depends(get_current_employee_id),
    db: AsyncSession = Depends(get_db),
) -> ResponseModel[SupplierItemResponse]:
    """接收供应商信息，并使用统一响应格式返回创建后的供应商信息。"""

    # request是前端提交的创建内容；Service负责权限、数据和重复值校验。
    created_supplier = await create_supplier_service(
        request=request,
        current_employee_id=current_employee_id,
        db=db,
    )

    return ResponseModel[SupplierItemResponse](
        message="创建供应商成功",
        data=created_supplier,
    )


# endregion
__all__ = ["suppliers_router"]
