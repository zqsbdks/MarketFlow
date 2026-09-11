"""进货管理 API 路由。"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies.auth import get_current_employee_id
from app.dependencies.db import get_db
from app.schemas.base import ResponseModel
from app.schemas.purchases_requests import PurchasesListRequest
from app.schemas.purchases_responses import PurchaseListResponse
from app.services.purchases import get_purchases_list_service

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


__all__ = ["purchases_router"]
