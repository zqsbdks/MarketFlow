"""销售记录业务逻辑。"""

from datetime import datetime, time
from decimal import Decimal

from fastapi import HTTPException, Request
from fastapi import status as http_status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.business_time import business_now
from app.crud import sales as data_access
from app.crud.auth import get_employee_by_id
from app.crud.business_sequence import next_business_sequence
from app.crud.operation_audit_logs import create_operation_audit_log
from app.crud.sales import (
    InsufficientStockError,
    get_sale_by_client_request_id,
    get_sales_detail,
    get_sales_list,
)
from app.crud.stores import department_is_enabled, first_active_store_id, get_store_by_id
from app.models.discount_rule import DiscountRule
from app.models.enums import (
    DiscountType,
    EmployeeRole,
    InventoryBatchStatus,
    ProductStatus,
    SaleSource,
)
from app.models.sale import Sale
from app.models.sale_item import SaleItem
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
    *,
    http_request: Request | None = None,
) -> SalesListResponse:
    """验证当前员工和日期范围，并组装销售单分页列表。"""

    # 本接口在服务层明确检查店铺范围；不依赖数据库自动事件。
    if http_request is not None:
        access_employee = await get_employee_by_id(employee_id=current_employee_id, db=db)
        if access_employee is None or not access_employee.is_active:
            raise HTTPException(401, "账号不存在或已停用")
        is_headquarters = access_employee.role == EmployeeRole.HEADQUARTERS
        selected_store_id = access_employee.store_id
        raw_store_id = http_request.headers.get("X-Store-ID")
        if not raw_store_id:
            raw_store_id = http_request.query_params.get("store_id")
        if raw_store_id == "all":
            raise HTTPException(403, "此接口不支持全公司汇总")
        elif raw_store_id:
            try:
                selected_store_id = int(raw_store_id)
            except ValueError as error:
                raise HTTPException(422, "门店ID无效") from error
            if selected_store_id <= 0:
                raise HTTPException(422, "门店ID无效")
        if selected_store_id is None and is_headquarters and raw_store_id != "all":
            selected_store_id = await first_active_store_id(db)
        if selected_store_id is not None:
            selected_store = await get_store_by_id(selected_store_id, db)
            if selected_store is None or not selected_store.is_active:
                raise HTTPException(403, "门店不存在或已停用")
        if not is_headquarters and access_employee.store_id is None:
            raise HTTPException(403, "员工尚未分配门店")

        # 这里只记录本次查询参数；CRUD 会明确读取并添加 store_id 条件。
        db.info.update(
            actor_id=access_employee.id,
            actor_role=access_employee.role,
            own_store_id=access_employee.store_id,
            read_store_id=selected_store_id,
            write_store_id=access_employee.store_id,
            company_management=False,
            company_catalog_read=False,
            private_employee_path=False,
            store_context=True,
        )
        http_request.state.store_id = selected_store_id
        http_request.state.employee_id = access_employee.id
        http_request.state.own_store_id = access_employee.store_id

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

        response_items_set = set()
        for response_items_item in sale.items:
            response_items_set.add(response_items_item.product_id)
        response_items = response_items_set
        sale_item = SalesItemResponse(
            sale_no=sale.sale_no,
            sold_at=sale.sold_at,
            original_total_amount=sale.original_total_amount,
            discount_amount=sale.discount_amount,
            total_amount=sale.total_amount,
            total_quantity=total_quantity,
            # 同一商品可能因为跨批次被拆成多条明细，种类数按商品ID去重。
            item_count=len(response_items),
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
    *,
    http_request: Request | None = None,
) -> SalePricePreviewResponse:
    """验证收银员工，并按当前生效规则计算价格但不扣库存、不创建销售单。"""

    # 本接口在服务层明确检查店铺范围；不依赖数据库自动事件。
    if http_request is not None:
        access_employee = await get_employee_by_id(employee_id=current_employee_id, db=db)
        if access_employee is None or not access_employee.is_active:
            raise HTTPException(401, "账号不存在或已停用")
        is_headquarters = access_employee.role == EmployeeRole.HEADQUARTERS
        selected_store_id = access_employee.store_id
        raw_store_id = http_request.headers.get("X-Store-ID")
        if not raw_store_id:
            raw_store_id = http_request.query_params.get("store_id")
        if raw_store_id == "all":
            raise HTTPException(403, "此接口不支持全公司汇总")
        elif raw_store_id:
            try:
                selected_store_id = int(raw_store_id)
            except ValueError as error:
                raise HTTPException(422, "门店ID无效") from error
            if selected_store_id <= 0:
                raise HTTPException(422, "门店ID无效")
        if selected_store_id is None and is_headquarters and raw_store_id != "all":
            selected_store_id = await first_active_store_id(db)
        if selected_store_id is not None:
            selected_store = await get_store_by_id(selected_store_id, db)
            if selected_store is None or not selected_store.is_active:
                raise HTTPException(403, "门店不存在或已停用")
        if not is_headquarters and access_employee.store_id is None:
            raise HTTPException(403, "员工尚未分配门店")

        # 这里只记录本次查询参数；CRUD 会明确读取并添加 store_id 条件。
        db.info.update(
            actor_id=access_employee.id,
            actor_role=access_employee.role,
            own_store_id=access_employee.store_id,
            read_store_id=selected_store_id,
            write_store_id=access_employee.store_id,
            company_management=False,
            company_catalog_read=False,
            private_employee_path=False,
            store_context=True,
        )
        http_request.state.store_id = selected_store_id
        http_request.state.employee_id = access_employee.id
        http_request.state.own_store_id = access_employee.store_id

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
    now = business_now()
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

        if rule is not None:
            discount_rule_id_value = rule.id
        else:
            discount_rule_id_value = None
        if rule is not None:
            discount_rule_name_value = rule.name
        else:
            discount_rule_name_value = None
        if rule is not None:
            discount_type_value = rule.discount_type
        else:
            discount_type_value = None
        if rule is not None:
            discount_value_value = rule.discount_value
        else:
            discount_value_value = None
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
                discount_rule_id=discount_rule_id_value,
                discount_rule_name=discount_rule_name_value,
                discount_type=discount_type_value,
                discount_value=discount_value_value,
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
    *,
    http_request: Request | None = None,
) -> SaleDetailResponse:
    """验证收银员工，在营业时间内创建销售并扣减未过期批次库存。"""

    # 本接口在服务层明确检查店铺范围；不依赖数据库自动事件。
    if http_request is not None:
        access_employee = await get_employee_by_id(employee_id=current_employee_id, db=db)
        if access_employee is None or not access_employee.is_active:
            raise HTTPException(401, "账号不存在或已停用")
        is_headquarters = access_employee.role == EmployeeRole.HEADQUARTERS
        selected_store_id = access_employee.store_id
        raw_store_id = http_request.headers.get("X-Store-ID")
        if not raw_store_id:
            raw_store_id = http_request.query_params.get("store_id")
        if raw_store_id == "all":
            raise HTTPException(403, "此接口不支持全公司汇总")
        elif raw_store_id:
            try:
                selected_store_id = int(raw_store_id)
            except ValueError as error:
                raise HTTPException(422, "门店ID无效") from error
            if selected_store_id <= 0:
                raise HTTPException(422, "门店ID无效")
        if selected_store_id is None and is_headquarters and raw_store_id != "all":
            selected_store_id = await first_active_store_id(db)
        if selected_store_id is not None:
            selected_store = await get_store_by_id(selected_store_id, db)
            if selected_store is None or not selected_store.is_active:
                raise HTTPException(403, "门店不存在或已停用")
        if not is_headquarters and access_employee.store_id is None:
            raise HTTPException(403, "员工尚未分配门店")
        if is_headquarters:
            raise HTTPException(403, "总部不执行门店日常业务")
        if selected_store_id != access_employee.store_id:
            raise HTTPException(403, "跨店查看为只读，不能修改其他门店")
        # 这里只记录本次查询参数；CRUD 会明确读取并添加 store_id 条件。
        db.info.update(
            actor_id=access_employee.id,
            actor_role=access_employee.role,
            own_store_id=access_employee.store_id,
            read_store_id=selected_store_id,
            write_store_id=access_employee.store_id,
            company_management=False,
            company_catalog_read=False,
            private_employee_path=False,
            store_context=True,
        )
        http_request.state.store_id = selected_store_id
        http_request.state.employee_id = access_employee.id
        http_request.state.own_store_id = access_employee.store_id

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

    # 相同幂等ID已完成结账时直接返回原小票，避免双击按钮重复扣减库存。
    if request.client_request_id:
        request_id = str(request.client_request_id)
    else:
        request_id = None
    if request_id:
        existing_sale = await get_sale_by_client_request_id(request_id, db)
        if existing_sale is not None:
            return _build_sale_detail_response(existing_sale)

    # 第二步：销售时间由服务器生成，前端不能伪造历史销售时间。
    sold_at = business_now()
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
            client_request_id=request_id,
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
    except IntegrityError as exc:
        await db.rollback()
        if request_id:
            existing_sale = await get_sale_by_client_request_id(request_id, db)
            if existing_sale is not None:
                return _build_sale_detail_response(existing_sale)
        raise HTTPException(
            status_code=http_status.HTTP_409_CONFLICT,
            detail="销售请求重复或销售单号冲突，请刷新后重试",
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
    sale_no: str, db: AsyncSession, current_employee_id: int, *, http_request: Request | None = None
) -> SaleDetailResponse:
    """验证当前员工，并组装指定销售单及其商品明细。"""

    # 本接口在服务层明确检查店铺范围；不依赖数据库自动事件。
    if http_request is not None:
        access_employee = await get_employee_by_id(employee_id=current_employee_id, db=db)
        if access_employee is None or not access_employee.is_active:
            raise HTTPException(401, "账号不存在或已停用")
        is_headquarters = access_employee.role == EmployeeRole.HEADQUARTERS
        selected_store_id = access_employee.store_id
        raw_store_id = http_request.headers.get("X-Store-ID")
        if not raw_store_id:
            raw_store_id = http_request.query_params.get("store_id")
        if raw_store_id == "all":
            raise HTTPException(403, "此接口不支持全公司汇总")
        elif raw_store_id:
            try:
                selected_store_id = int(raw_store_id)
            except ValueError as error:
                raise HTTPException(422, "门店ID无效") from error
            if selected_store_id <= 0:
                raise HTTPException(422, "门店ID无效")
        if selected_store_id is None and is_headquarters and raw_store_id != "all":
            selected_store_id = await first_active_store_id(db)
        if selected_store_id is not None:
            selected_store = await get_store_by_id(selected_store_id, db)
            if selected_store is None or not selected_store.is_active:
                raise HTTPException(403, "门店不存在或已停用")
        if not is_headquarters and access_employee.store_id is None:
            raise HTTPException(403, "员工尚未分配门店")

        # 这里只记录本次查询参数；CRUD 会明确读取并添加 store_id 条件。
        db.info.update(
            actor_id=access_employee.id,
            actor_role=access_employee.role,
            own_store_id=access_employee.store_id,
            read_store_id=selected_store_id,
            write_store_id=access_employee.store_id,
            company_management=False,
            company_catalog_read=False,
            private_employee_path=False,
            store_context=True,
        )
        http_request.state.store_id = selected_store_id
        http_request.state.employee_id = access_employee.id
        http_request.state.own_store_id = access_employee.store_id

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


async def create_sale(
    requested_quantities: dict[int, int],
    final_unit_prices: dict[int, Decimal],
    applied_discount_rules: dict[int, DiscountRule | None],
    sold_at: datetime,
    employee_id: int,
    client_request_id: str | None,
    db: AsyncSession,
) -> Sale:
    """按先到期先销售原则扣减批次库存，并创建销售单和批次级明细。"""
    original_total_amount = Decimal("0.00")
    total_discount_amount = Decimal("0.00")
    total_amount = Decimal("0.00")
    total_cost = Decimal("0.00")
    sale_items: list[SaleItem] = []
    for product_id in sorted(requested_quantities):
        requested_quantity = requested_quantities[product_id]
        product = await data_access.get_sale_product_for_update(db=db, product_id=product_id)
        if product is None:
            raise LookupError(product_id)

        # 保存前直接检查门店部门配置。
        if db.info.get("store_context"):
            if not await department_is_enabled(product.store_id, product.department_id, db):
                raise HTTPException(400, "本店未启用此部门")
        if product.status != ProductStatus.ON_SALE:
            raise PermissionError(product.name)
        original_unit_price = product.sale_price.quantize(Decimal("0.01"))
        final_unit_price = final_unit_prices.get(product.id, original_unit_price)
        if final_unit_price > original_unit_price:
            final_unit_price = original_unit_price
        applied_rule = applied_discount_rules.get(product.id)
        batches = list(
            (await data_access.get_saleable_batches_for_update(db=db, product_id=product_id)).all()
        )
        available_quantity = sum(batch.remaining_quantity for batch in batches)
        if available_quantity < requested_quantity:
            raise InsufficientStockError(
                product_name=product.name,
                requested=requested_quantity,
                available=available_quantity,
            )
        quantity_left = requested_quantity
        for batch in batches:
            if quantity_left == 0:
                break
            before_batch_quantity = batch.remaining_quantity
            before_batch_status = batch.status
            deducted_quantity = min(batch.remaining_quantity, quantity_left)
            batch.remaining_quantity -= deducted_quantity
            if batch.remaining_quantity == 0:
                batch.status = InventoryBatchStatus.SOLD_OUT
            unit_cost = batch.purchase_item.unit_cost
            original_subtotal = original_unit_price * deducted_quantity
            subtotal = final_unit_price * deducted_quantity
            discount_amount = original_subtotal - subtotal
            cost_subtotal = unit_cost * deducted_quantity
            if applied_rule is not None:
                discount_rule_id_value_item = applied_rule.id
            else:
                discount_rule_id_value_item = None
            if applied_rule is not None:
                discount_rule_name_snapshot_value = applied_rule.name
            else:
                discount_rule_name_snapshot_value = None
            if applied_rule is not None:
                discount_type_snapshot_value = applied_rule.discount_type.value
            else:
                discount_type_snapshot_value = None
            if applied_rule is not None:
                discount_value_snapshot_value = applied_rule.discount_value
            else:
                discount_value_snapshot_value = None
            sale_items.append(
                SaleItem(
                    store_id=db.info.get("write_store_id") or 1,
                    product_id=product.id,
                    inventory_batch_id=batch.id,
                    product_no_snapshot=product.product_no,
                    product_name_snapshot=product.name,
                    department_id=product.department_id,
                    quantity=deducted_quantity,
                    original_unit_price=original_unit_price,
                    unit_price=final_unit_price,
                    discount_amount=discount_amount,
                    discount_rule_id=discount_rule_id_value_item,
                    discount_rule_name_snapshot=discount_rule_name_snapshot_value,
                    discount_type_snapshot=discount_type_snapshot_value,
                    discount_value_snapshot=discount_value_snapshot_value,
                    unit_cost=unit_cost,
                    subtotal=subtotal,
                    cost_subtotal=cost_subtotal,
                )
            )
            original_total_amount += original_subtotal
            total_discount_amount += discount_amount
            total_amount += subtotal
            total_cost += cost_subtotal
            quantity_left -= deducted_quantity
            await create_operation_audit_log(
                employee_id=employee_id,
                module="inventory",
                action="sale_deduction",
                target_type="inventory_batch",
                target_id=batch.id,
                before_data={
                    "remaining_quantity": before_batch_quantity,
                    "status": before_batch_status,
                },
                after_data={
                    "remaining_quantity": batch.remaining_quantity,
                    "status": batch.status,
                    "deducted_quantity": deducted_quantity,
                },
                reason="创建销售单时自动扣减库存",
                db=db,
            )
        before_product_stock = product.stock_quantity
        await db.flush()
        product.stock_quantity = int(
            await data_access.get_product_stock_total(db=db, product=product) or 0
        )
        await create_operation_audit_log(
            employee_id=employee_id,
            module="product",
            action="sync_stock_after_sale",
            target_type="product",
            target_id=product.id,
            before_data={"stock_quantity": before_product_stock},
            after_data={"stock_quantity": product.stock_quantity},
            reason="销售扣减批次后重新汇总商品库存",
            db=db,
        )
    sale_no_prefix = f"S{sold_at:%Y%m%d}"
    next_number = await next_business_sequence(f"sale:{sold_at:%Y%m%d}", db)
    sale = Sale(
        store_id=db.info.get("write_store_id") or 1,
        sale_no=f"{sale_no_prefix}{next_number:04d}",
        client_request_id=client_request_id,
        sold_at=sold_at,
        original_total_amount=original_total_amount,
        discount_amount=total_discount_amount,
        total_amount=total_amount,
        total_cost=total_cost,
        gross_profit=total_amount - total_cost,
        source=SaleSource.POS,
        items=sale_items,
    )
    data_access.add_sale_record(db=db, sale=sale)
    await db.flush()
    items_value_values = []
    for items_value_item in sale.items:
        items_value_values.append(
            {
                "sale_item_id": items_value_item.id,
                "product_id": items_value_item.product_id,
                "inventory_batch_id": items_value_item.inventory_batch_id,
                "quantity": items_value_item.quantity,
                "original_unit_price": items_value_item.original_unit_price,
                "unit_price": items_value_item.unit_price,
                "discount_amount": items_value_item.discount_amount,
                "discount_rule_id": items_value_item.discount_rule_id,
                "subtotal": items_value_item.subtotal,
            }
        )
    items_value = items_value_values
    await create_operation_audit_log(
        employee_id=employee_id,
        module="sale",
        action="create",
        target_type="sale",
        target_id=sale.id,
        before_data=None,
        after_data={
            "sale_no": sale.sale_no,
            "original_total_amount": sale.original_total_amount,
            "discount_amount": sale.discount_amount,
            "total_amount": sale.total_amount,
            "total_cost": sale.total_cost,
            "gross_profit": sale.gross_profit,
            "item_count": len(sale.items),
            "sold_at": sale.sold_at,
            "items": items_value,
        },
        reason=None,
        db=db,
    )
    return sale
