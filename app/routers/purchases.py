"""进货管理 API 路由。"""

from fastapi import APIRouter, Depends, Path
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies.auth import get_current_employee_id
from app.dependencies.db import get_db
from app.schemas.base import ResponseModel
from app.schemas.purchases_requests import CreatePurchaseRequest, PurchasesListRequest
from app.schemas.purchases_responses import (
    PurchaseDetailResponse,
    PurchaseListResponse,
)
from app.services.purchases import (
    auto_receive_purchases_service,
    create_purchase_service,
    get_purchase_detail_service,
    get_purchases_list_service,
)

# 最终接口地址统一以 /api/v1/purchases 开头。
purchases_router = APIRouter(
    prefix="/purchases",
    tags=["purchases"],
)


# 后续接口建议按以下顺序编写：
# 1. GET /list：获取进货单列表
# 2. GET /{purchase_id}：获取进货单详情
# 3. POST /：创建进货单
# 4. PUT /{purchase_id}/receive：签收到货


# region 获取进货单列表
@purchases_router.get(
    "/list",
    response_model=ResponseModel[PurchaseListResponse],
    summary="获取进货单列表",
    description="分页获取进货单，并可按单号、部门、下单日期和状态筛选。",
)
async def list_purchases(
    request: PurchasesListRequest = Depends(),
    db: AsyncSession = Depends(get_db),
    current_employee_id: int = Depends(get_current_employee_id),
) -> ResponseModel[PurchaseListResponse]:
    """接收列表查询参数，并使用统一响应格式返回进货单列表。"""

    purchases = await get_purchases_list_service(
        page=request.page,
        page_size=request.page_size,
        purchase_no=request.purchase_no,
        department_id=request.department_id,
        ordered_at=request.ordered_at,
        arrived_at=request.arrived_at,
        purchase_status=request.status,
        current_employee_id=current_employee_id,
        db=db,
    )
    return ResponseModel[PurchaseListResponse](
        message="获取进货单列表成功",
        data=purchases,
    )


# endregion


# region 自动签收进货单
@purchases_router.put(
    "/auto-receive",
    response_model=ResponseModel[list[PurchaseDetailResponse]],
    summary="自动签收到期进货单",
    description="签收所有已达到预计到货时间的待到货进货单，并同步商品和批次库存。",
)
async def auto_receive_purchases(
    current_employee_id: int = Depends(get_current_employee_id),
    db: AsyncSession = Depends(get_db),
) -> ResponseModel[list[PurchaseDetailResponse]]:
    """模拟每天12点执行的自动签收任务；当前由店长调用接口触发。"""

    purchases = await auto_receive_purchases_service(
        current_employee_id=current_employee_id,
        db=db,
    )
    return ResponseModel[list[PurchaseDetailResponse]](
        message=f"自动签收完成，共签收{len(purchases)}张进货单",
        data=purchases,
    )


# endregion


# region 获取进货单详情
@purchases_router.get(
    "/{purchase_id}",
    response_model=ResponseModel[PurchaseDetailResponse],
    summary="获取进货单详情",
    description="获取进货单详情。",
)
async def get_purchase_detail(
    purchase_id: int = Path(..., description="进货单ID", ge=1),
    current_employee_id: int = Depends(get_current_employee_id),
    db: AsyncSession = Depends(get_db),
) -> ResponseModel[PurchaseDetailResponse]:
    """接收进货单ID，并返回进货单汇总及商品明细。"""

    purchase = await get_purchase_detail_service(
        purchase_id=purchase_id,
        current_employee_id=current_employee_id,
        db=db,
    )
    return ResponseModel[PurchaseDetailResponse](
        message="获取进货单详情成功",
        data=purchase,
    )


# endregion


# region 创建进货单
@purchases_router.post(
    "/",
    response_model=ResponseModel[PurchaseDetailResponse],
    summary="创建进货单",
    description="创建进货单。",
)
async def create_purchase(
    request: CreatePurchaseRequest,
    current_employee_id: int = Depends(get_current_employee_id),
    db: AsyncSession = Depends(get_db),
) -> ResponseModel[PurchaseDetailResponse]:
    """接收进货单汇总及商品明细，并返回进货单汇总及商品明细。"""

    purchase = await create_purchase_service(
        purchase=request,
        current_employee_id=current_employee_id,
        db=db,
    )
    return ResponseModel[PurchaseDetailResponse](message="创建进货单成功", data=purchase)


# endregion


__all__ = ["purchases_router"]
