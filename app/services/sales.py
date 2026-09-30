"""销售记录业务逻辑。"""

from datetime import datetime, time
from decimal import Decimal

from fastapi import HTTPException
from fastapi import status as http_status
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.auth import get_employee_by_id
from app.crud.sales import InsufficientStockError, create_sale, get_sales_detail, get_sales_list
from app.models.discount_rule import DiscountRule
from app.models.enums import DiscountType, ProductStatus
from app.models.sale import Sale
from app.schemas.sales_requests import CreateSaleRequest
from app.schemas.sales_responses import (
    SaleDetailItemResponse,
    SaleDetailResponse,
    SalePricePreviewResponse,
    SalesItemResponse,
    SalesListResponse,
)
from app.services.discount_rule import get_product_discount_prices

BUSINESS_OPENING_TIME = time(9, 0)
BUSINESS_CLOSING_TIME = time(21, 0)


# region 组装销售单详情响应
def _build_sale_detail_response(sale: Sale) -> SaleDetailResponse:
    """把同一商品因跨批次产生的多条数据库明细合并成小票中的一行。"""

    # key包含商品、原价、成交价和规则ID，防止不同折扣来源的明细被错误合并。
    grouped_items: dict[tuple[int, str, Decimal, Decimal, int | None], SaleDetailItemResponse] = {}
    for item in sale.items:
        key = (
            item.product_id,
            item.product_name_snapshot,
            item.original_unit_price,
            item.unit_price,
            item.discount_rule_id,
        )
        existing = grouped_items.get(key)
        if existing is None:
            # 第一次遇到该商品时，新建一行前端小票明细。
            discount_type = None
            if item.discount_type_snapshot is not None:
                discount_type = DiscountType(item.discount_type_snapshot)
            grouped_items[key] = SaleDetailItemResponse(
                product_id=item.product_id,
                product_name=item.product_name_snapshot,
                quantity=item.quantity,
                original_unit_price=item.original_unit_price,
                unit_price=item.unit_price,
                original_subtotal=item.original_unit_price * item.quantity,
                discount_amount=item.discount_amount,
                subtotal=item.subtotal,
                discount_rule_id=item.discount_rule_id,
                discount_rule_name=item.discount_rule_name_snapshot,
                discount_type=discount_type,
                discount_value=item.discount_value_snapshot,
            )
        else:
            # 同商品同折扣的其他批次只累加金额和数量，不增加重复小票行。
            existing.quantity += item.quantity
            existing.original_subtotal += item.original_unit_price * item.quantity
            existing.discount_amount += item.discount_amount
            existing.subtotal += item.subtotal

    return SaleDetailResponse(
        sale_no=sale.sale_no,
        sold_at=sale.sold_at,
        original_total_amount=sale.original_total_amount,
        discount_amount=sale.discount_amount,
        total_amount=sale.total_amount,
        items=list(grouped_items.values()),
    )


# endregion


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
            original_total_amount=sale.original_total_amount,
            discount_amount=sale.discount_amount,
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


# region 预览销售价格
async def preview_sale_price_service(
    request: CreateSaleRequest,
    current_employee_id: int,
    db: AsyncSession,
) -> SalePricePreviewResponse:
    """验证收银员工，并按当前生效规则计算价格但不扣库存、不创建销售单。"""

    # 第一步：价格预览也属于内部收银功能，因此需要验证员工账号状态。
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

    # 第二步：合并重复扫码的商品数量。
    requested_quantities: dict[int, int] = {}
    for item in request.items:
        old_quantity = requested_quantities.get(item.product_id, 0)
        requested_quantities[item.product_id] = old_quantity + item.quantity

    # 第三步：使用统一折扣函数取得每件商品当前最低成交价。
    now = datetime.now()
    product_ids = list(requested_quantities.keys())
    prices = await get_product_discount_prices(product_ids=product_ids, now=now, db=db)

    preview_items: list[SaleDetailItemResponse] = []
    original_total_amount = Decimal("0.00")
    total_amount = Decimal("0.00")
    for product_id in product_ids:
        price = prices.get(product_id)
        if price is None:
            raise HTTPException(
                status_code=http_status.HTTP_404_NOT_FOUND,
                detail=f"商品ID {product_id} 不存在",
            )
        if price.product.status != ProductStatus.ON_SALE:
            raise HTTPException(
                status_code=http_status.HTTP_400_BAD_REQUEST,
                detail=f"商品“{price.product.name}”当前已停售",
            )

        quantity = requested_quantities[product_id]
        original_subtotal = price.original_unit_price * quantity
        subtotal = price.final_unit_price * quantity
        discount_amount = original_subtotal - subtotal
        rule = price.discount_rule

        preview_items.append(
            SaleDetailItemResponse(
                product_id=price.product.id,
                product_name=price.product.name,
                quantity=quantity,
                original_unit_price=price.original_unit_price,
                unit_price=price.final_unit_price,
                original_subtotal=original_subtotal,
                discount_amount=discount_amount,
                subtotal=subtotal,
                discount_rule_id=rule.id if rule is not None else None,
                discount_rule_name=rule.name if rule is not None else None,
                discount_type=rule.discount_type if rule is not None else None,
                discount_value=rule.discount_value if rule is not None else None,
            )
        )
        original_total_amount += original_subtotal
        total_amount += subtotal

    return SalePricePreviewResponse(
        original_total_amount=original_total_amount,
        discount_amount=original_total_amount - total_amount,
        total_amount=total_amount,
        items=preview_items,
    )


# endregion


# region 创建销售单
async def create_sale_service(
    # request：收银台扫码后提交的商品ID和数量列表。
    request: CreateSaleRequest,
    # current_employee_id：从登录令牌中解析出的当前收银员工ID。
    current_employee_id: int,
    # db：当前 HTTP 请求使用的异步数据库会话。
    db: AsyncSession,
) -> SaleDetailResponse:
    """验证收银员工，在营业时间内创建销售并扣减未过期批次库存。"""

    # 第一步：验证操作员工存在、账号启用并且已经修改初始密码。
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

    # 第二步：销售时间由服务器生成，前端不能伪造历史销售时间。
    sold_at = datetime.now()
    if not BUSINESS_OPENING_TIME <= sold_at.time() <= BUSINESS_CLOSING_TIME:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail="只能在营业时间09:00至21:00创建销售单",
        )

    # 第三步：同一商品被扫码多次时先合并数量，避免重复锁定和扣减同一组批次。
    requested_quantities: dict[int, int] = {}
    for item in request.items:
        requested_quantities[item.product_id] = (
            requested_quantities.get(item.product_id, 0) + item.quantity
        )

    # 第四步：按照真正结账时间重新计算折扣，不能直接相信前端预览价格。
    product_ids = list(requested_quantities.keys())
    prices = await get_product_discount_prices(product_ids=product_ids, now=sold_at, db=db)
    final_unit_prices: dict[int, Decimal] = {}
    applied_discount_rules: dict[int, DiscountRule | None] = {}
    for product_id in product_ids:
        price = prices.get(product_id)
        if price is None:
            raise HTTPException(
                status_code=http_status.HTTP_404_NOT_FOUND,
                detail=f"商品ID {product_id} 不存在",
            )
        final_unit_prices[product_id] = price.final_unit_price
        applied_discount_rules[product_id] = price.discount_rule

    # 第五步：扣库存、创建销售单和明细；成功后在Service层统一提交事务。
    try:
        sale = await create_sale(
            requested_quantities=requested_quantities,
            final_unit_prices=final_unit_prices,
            applied_discount_rules=applied_discount_rules,
            sold_at=sold_at,
            employee_id=current_employee_id,
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
    except Exception:
        # 未预料的数据库或程序异常同样必须回滚，不能留下部分扣减的数据。
        await db.rollback()
        raise

    # 第六步：重新查询已经提交的销售单，并按商品合并跨批次明细后返回小票。
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
    "preview_sale_price_service",
]
