"""销售记录业务逻辑。"""

from datetime import datetime, time

from fastapi import HTTPException
from fastapi import status as http_status
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.auth import get_employee_by_id
from app.crud.sales import get_sales_list
from app.schemas.sales_responses import SalesItemResponse, SalesListResponse

BUSINESS_OPENING_TIME = time(9, 0)
BUSINESS_CLOSING_TIME = time(21, 0)


# region 获取销售单列表
async def get_sales_list_service(
    page: int,
    page_size: int,
    start_time: datetime | None,
    end_time: datetime | None,
    sale_no: str | None,
    current_employee_id: int,
    db: AsyncSession,
) -> SalesListResponse:
    """验证当前员工和日期范围，并组装销售单分页列表。"""

    employee = await get_employee_by_id(
        employee_id=current_employee_id,
        db=db,
    )
    if employee is None:
        raise HTTPException(
            status_code=http_status.HTTP_401_UNAUTHORIZED,
            detail="当前登录员工不存在",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not employee.is_active:
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail="账号已停用",
        )

    if employee.must_change_password:
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail="请先修改初始密码",
        )

    # 查询时间只能选择门店营业时间 09:00 至 21:00。
    if start_time is not None:
        selected_start_time = start_time.time()
        if not BUSINESS_OPENING_TIME <= selected_start_time <= BUSINESS_CLOSING_TIME:
            raise HTTPException(
                status_code=http_status.HTTP_400_BAD_REQUEST,
                detail="开始时间必须在09:00至21:00之间",
            )

    if end_time is not None:
        selected_end_time = end_time.time()
        if not BUSINESS_OPENING_TIME <= selected_end_time <= BUSINESS_CLOSING_TIME:
            raise HTTPException(
                status_code=http_status.HTTP_400_BAD_REQUEST,
                detail="结束时间必须在09:00至21:00之间",
            )

    if start_time is not None and end_time is not None and start_time >= end_time:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail="开始时间必须早于结束时间",
        )

    sales, total = await get_sales_list(
        page=page,
        page_size=page_size,
        start_time=start_time,
        end_time=end_time,
        sale_no=sale_no,
        db=db,
    )

    # 分步处理每张销售单，统计其中的商品总数量和明细种类数。
    sale_items: list[SalesItemResponse] = []
    for sale in sales:
        total_quantity = 0
        for item in sale.items:
            total_quantity += item.quantity

        sale_item = SalesItemResponse(
            sale_no=sale.sale_no,
            sold_at=sale.sold_at,
            total_amount=sale.total_amount,
            total_quantity=total_quantity,
            item_count=len(sale.items),
        )
        sale_items.append(sale_item)

    total_pages = (total + page_size - 1) // page_size

    return SalesListResponse(
        items=sale_items,
        page=page,
        page_size=page_size,
        total=total,
        total_pages=total_pages,
    )


# endregion


__all__ = [
    "BUSINESS_CLOSING_TIME",
    "BUSINESS_OPENING_TIME",
    "get_sales_list_service",
]
