"""销售记录业务逻辑。"""

from datetime import datetime, time

from fastapi import HTTPException
from fastapi import status as http_status
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.auth import get_employee_by_id
from app.crud.sales import InsufficientStockError, create_sale, get_sales_detail, get_sales_list
from app.schemas.sales_requests import CreateSaleRequest
from app.schemas.sales_responses import (
    SaleDetailItemResponse,
    SaleDetailResponse,
    SalesItemResponse,
    SalesListResponse,
)

BUSINESS_OPENING_TIME = time(9, 0)
BUSINESS_CLOSING_TIME = time(21, 0)


def _build_sale_detail_response(sale) -> SaleDetailResponse:
    """把同一商品因跨批次产生的多条数据库明细合并成小票中的一行。"""

    grouped_items: dict[tuple[int, str, object], SaleDetailItemResponse] = {}
    for item in sale.items:
        key = (item.product_id, item.product_name_snapshot, item.unit_price)
        existing = grouped_items.get(key)
        if existing is None:
            grouped_items[key] = SaleDetailItemResponse(
                product_name=item.product_name_snapshot,
                quantity=item.quantity,
                unit_price=item.unit_price,
                subtotal=item.subtotal,
            )
        else:
            existing.quantity += item.quantity
            existing.subtotal += item.subtotal

    return SaleDetailResponse(
        sale_no=sale.sale_no,
        sold_at=sale.sold_at,
        total_amount=sale.total_amount,
        items=list(grouped_items.values()),
    )


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
            # 同一商品可能因为跨批次被拆成多条明细，种类数按商品ID去重。
            item_count=len({item.product_id for item in sale.items}),
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


# region 创建销售单
async def create_sale_service(
    request: CreateSaleRequest,
    current_employee_id: int,
    db: AsyncSession,
) -> SaleDetailResponse:
    """验证收银员工，在营业时间内创建销售并扣减未过期批次库存。"""

    employee = await get_employee_by_id(employee_id=current_employee_id, db=db)
    if employee is None:
        raise HTTPException(
            status_code=http_status.HTTP_401_UNAUTHORIZED,
            detail="当前登录员工不存在",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not employee.is_active:
        raise HTTPException(status_code=http_status.HTTP_403_FORBIDDEN, detail="账号已停用")
    if employee.must_change_password:
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail="请先修改初始密码",
        )

    sold_at = datetime.now()
    if not BUSINESS_OPENING_TIME <= sold_at.time() <= BUSINESS_CLOSING_TIME:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail="只能在营业时间09:00至21:00创建销售单",
        )

    # 同一商品被扫码多次时先合并数量，避免重复读取和扣减同一组批次。
    requested_quantities: dict[int, int] = {}
    for item in request.items:
        requested_quantities[item.product_id] = (
            requested_quantities.get(item.product_id, 0) + item.quantity
        )

    try:
        sale = await create_sale(
            requested_quantities=requested_quantities,
            sold_at=sold_at,
            db=db,
        )
        await db.commit()
    except LookupError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail=f"商品ID {exc.args[0]} 不存在",
        ) from exc
    except PermissionError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail=f"商品“{exc.args[0]}”当前已停售",
        ) from exc
    except InsufficientStockError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail=(
                f"商品“{exc.product_name}”可销售库存不足："
                f"需要{exc.requested}件，当前只有{exc.available}件"
            ),
        ) from exc

    refreshed_sale = await get_sales_detail(sale_no=sale.sale_no, db=db)
    if refreshed_sale is None:
        raise RuntimeError("销售单创建后无法重新查询")
    return _build_sale_detail_response(refreshed_sale)


# endregion


# region 获取销售单详情
async def get_sales_detail_service(
    sale_no: str,
    db: AsyncSession,
    current_employee_id: int,
) -> SaleDetailResponse:
    """验证当前员工，并组装指定销售单及其商品明细。"""

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

    sale = await get_sales_detail(sale_no=sale_no, db=db)
    if sale is None:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail="销售单不存在",
        )

    return _build_sale_detail_response(sale)


# endregion


__all__ = [
    "BUSINESS_CLOSING_TIME",
    "BUSINESS_OPENING_TIME",
    "create_sale_service",
    "get_sales_detail_service",
    "get_sales_list_service",
]
