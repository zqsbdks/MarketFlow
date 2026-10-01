"""折扣规则与适用范围业务逻辑。"""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from fastapi import HTTPException
from fastapi import status as http_status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.business_time import business_now
from app.crud.auth import get_employee_by_id
from app.crud.discount_rule import (
    create_discount_rule,
    create_discount_rule_product_scopes,
    delete_discount_rule_product_scopes,
    delete_discount_rules,
    get_active_discount_rules_for_products,
    get_discount_products_by_ids,
    get_discount_rule_by_id,
    get_discount_rule_by_name,
    get_discount_rule_product_scope,
    get_discount_rule_product_scopes_for_delete,
    get_discount_rule_products_list,
    get_discount_rules_for_delete,
    get_discount_rules_list,
    get_existing_discount_product_ids,
    update_discount_rule,
    update_discount_rule_status,
)
from app.crud.employees import get_department_by_id
from app.crud.operation_audit_logs import create_operation_audit_log
from app.models.discount_rule import DiscountRule
from app.models.enums import (
    DiscountComputedStatus,
    DiscountScheduleType,
    DiscountScopeType,
    DiscountType,
    EmployeeRole,
)
from app.models.product import Product
from app.schemas.discount_rule_requests import (
    AddDiscountRuleProductsRequest,
    CreateDiscountRuleRequest,
    GetDiscountRuleProductsRequest,
    UpdateDiscountRuleRequest,
    UpdateDiscountRuleStatusRequest,
)
from app.schemas.discount_rule_responses import (
    AddDiscountRuleProductsResponse,
    DeleteDiscountRuleProductsResponse,
    DeleteDiscountRulesResponse,
    DiscountRuleListItemResponse,
    DiscountRuleListResponse,
    DiscountRuleProductItemResponse,
    DiscountRuleProductListResponse,
)


# region 计算折扣规则当前状态
def calculate_discount_rule_status(
    rule: DiscountRule,
    now: datetime,
) -> DiscountComputedStatus:
    """根据人工开关和当前时间计算一条折扣规则的展示状态。"""

    # 人工关闭的优先级最高，即使原活动时间已经结束，也显示“已停用”。
    if not rule.is_active:
        return DiscountComputedStatus.DISABLED

    if rule.schedule_type == DiscountScheduleType.ONCE:
        # 单次活动超过结束时间后永久显示“已结束”。
        if rule.ends_at is not None and now >= rule.ends_at:
            return DiscountComputedStatus.ENDED

        # 当前时间同时满足开始时间和结束时间，才表示单次活动正在生效。
        if (
            rule.starts_at is not None
            and rule.ends_at is not None
            and rule.starts_at <= now < rule.ends_at
        ):
            return DiscountComputedStatus.ACTIVE
        return DiscountComputedStatus.SCHEDULED

    # 每日和每周规则只比较当前时、分、秒，不比较具体日期。
    current_time = now.time().replace(microsecond=0)
    is_in_daily_time = (
        rule.daily_start_time is not None
        and rule.daily_end_time is not None
        and rule.daily_start_time <= current_time < rule.daily_end_time
    )

    if rule.schedule_type == DiscountScheduleType.DAILY:
        if is_in_daily_time:
            return DiscountComputedStatus.ACTIVE
        return DiscountComputedStatus.SCHEDULED

    # 每周规则还要求今天的星期数字包含在weekdays中。
    is_selected_weekday = now.isoweekday() in (rule.weekdays or [])
    if is_selected_weekday and is_in_daily_time:
        return DiscountComputedStatus.ACTIVE
    return DiscountComputedStatus.SCHEDULED


# endregion


# region 组装折扣规则响应
def _build_discount_rule_list_item(
    rule: DiscountRule,
    now: datetime,
) -> DiscountRuleListItemResponse:
    """将折扣规则ORM对象转换成前端需要的列表响应对象。"""

    return DiscountRuleListItemResponse(
        id=rule.id,
        name=rule.name,
        department_id=rule.department_id,
        department_name=rule.department.name,
        discount_type=rule.discount_type,
        discount_value=rule.discount_value,
        schedule_type=rule.schedule_type,
        starts_at=rule.starts_at,
        ends_at=rule.ends_at,
        daily_start_time=rule.daily_start_time,
        daily_end_time=rule.daily_end_time,
        weekdays=rule.weekdays,
        is_active=rule.is_active,
        computed_status=calculate_discount_rule_status(rule, now),
        created_by=rule.created_by,
        created_by_name=rule.creator.name,
        created_at=rule.created_at,
        updated_at=rule.updated_at,
    )


# endregion


# region 计算商品折后价
def _calculate_discounted_price(
    original_price: Decimal,
    discount_type: DiscountType,
    discount_value: Decimal,
) -> Decimal:
    """按照折扣方式计算商品价格，并统一保留两位小数。"""

    if discount_type == DiscountType.PERCENTAGE:
        discounted_price = original_price * discount_value
    elif discount_type == DiscountType.AMOUNT_OFF:
        # 立减金额大于商品原价时，最终价格最低为0元，不返回负数。
        discounted_price = max(original_price - discount_value, Decimal("0"))
    else:
        # fixed_price表示不再计算，直接把规则中的折扣数值作为成交单价。
        discounted_price = discount_value
    return discounted_price.quantize(Decimal("0.01"))


# endregion


# region 商品当前成交价格结果
@dataclass(frozen=True)
class ProductDiscountPrice:
    """保存一件商品在指定时间计算出的原价、成交价和选中规则。"""

    product: Product
    original_unit_price: Decimal
    final_unit_price: Decimal
    discount_rule: DiscountRule | None


# endregion


# region 计算多个商品当前最优折扣
async def get_product_discount_prices(
    product_ids: list[int],
    now: datetime,
    db: AsyncSession,
) -> dict[int, ProductDiscountPrice]:
    """为多个商品选择当前折后价最低的规则；折扣之间不叠加。"""

    # 第一步：去除重复商品ID，再一次性查询商品基础资料。
    unique_product_ids: list[int] = []
    for product_id in product_ids:
        if product_id not in unique_product_ids:
            unique_product_ids.append(product_id)

    products = await get_discount_products_by_ids(product_ids=unique_product_ids, db=db)

    # 第二步：整理商品、分类和部门ID，用一次查询取得所有候选规则。
    category_ids: list[int] = []
    department_ids: list[int] = []
    for product in products:
        if product.category_id not in category_ids:
            category_ids.append(product.category_id)
        if product.department_id not in department_ids:
            department_ids.append(product.department_id)

    rules = await get_active_discount_rules_for_products(
        product_ids=unique_product_ids,
        category_ids=category_ids,
        department_ids=department_ids,
        now=now,
        db=db,
    )

    # 第三步：逐个商品检查候选规则，默认成交价等于商品原销售价。
    prices: dict[int, ProductDiscountPrice] = {}
    for product in products:
        best_price = product.sale_price.quantize(Decimal("0.01"))
        best_rule: DiscountRule | None = None

        for rule in rules:
            rule_applies = False
            for scope in rule.scopes:
                if scope.scope_type == DiscountScopeType.PRODUCT and scope.product_id == product.id:
                    rule_applies = True
                elif (
                    scope.scope_type == DiscountScopeType.CATEGORY
                    and scope.category_id == product.category_id
                ):
                    rule_applies = True
                elif (
                    scope.scope_type == DiscountScopeType.DEPARTMENT
                    and scope.department_id == product.department_id
                ):
                    rule_applies = True

                if rule_applies:
                    break

            if not rule_applies:
                continue

            candidate_price = _calculate_discounted_price(
                original_price=product.sale_price,
                discount_type=rule.discount_type,
                discount_value=rule.discount_value,
            )
            # 名为折扣的规则不能提高售价；高于原价时按原价结算且不选中规则。
            if candidate_price < best_price:
                best_price = candidate_price
                best_rule = rule

        prices[product.id] = ProductDiscountPrice(
            product=product,
            original_unit_price=product.sale_price.quantize(Decimal("0.01")),
            final_unit_price=best_price,
            discount_rule=best_rule,
        )

    return prices


# endregion


# region 获取折扣规则列表
async def get_discount_rule_list_service(
    page: int,
    page_size: int,
    keyword: str | None,
    department_id: int | None,
    discount_type: DiscountType | None,
    schedule_type: DiscountScheduleType | None,
    is_active: bool | None,
    computed_status: DiscountComputedStatus | None,
    current_employee_id: int,
    db: AsyncSession,
) -> DiscountRuleListResponse:
    """验证当前账号，并返回经过筛选和分页的折扣规则列表。"""

    # 即使接口允许所有登录员工查询，也必须检查账号仍然存在且处于可用状态。
    current_employee = await get_employee_by_id(employee_id=current_employee_id, db=db)
    if current_employee is None:
        raise HTTPException(
            status_code=http_status.HTTP_401_UNAUTHORIZED,
            detail="当前登录员工不存在",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not current_employee.is_active:
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail="当前账号已停用",
        )
    if current_employee.must_change_password:
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail="请先修改初始密码",
        )

    # 同一次请求中的查询和响应组装必须共用同一个当前时间，避免临界点状态不一致。
    now = business_now()
    offset = (page - 1) * page_size
    rules, total = await get_discount_rules_list(
        offset=offset,
        page_size=page_size,
        keyword=keyword,
        department_id=department_id,
        discount_type=discount_type,
        schedule_type=schedule_type,
        is_active=is_active,
        computed_status=computed_status,
        now=now,
        db=db,
    )

    items = [_build_discount_rule_list_item(rule, now) for rule in rules]
    return DiscountRuleListResponse(
        items=items,
        page=page,
        page_size=page_size,
        total=total,
        total_pages=(total + page_size - 1) // page_size,
    )


# endregion


# region 获取折扣规则详情
async def get_discount_rule_detail_service(
    discount_rule_id: int,
    current_employee_id: int,
    db: AsyncSession,
) -> DiscountRuleListItemResponse:
    """验证当前账号，并返回指定折扣规则的完整资料和动态状态。"""

    # 详情接口允许所有正常登录的员工查询，但仍需验证账号的最新状态。
    current_employee = await get_employee_by_id(employee_id=current_employee_id, db=db)
    if current_employee is None:
        raise HTTPException(
            status_code=http_status.HTTP_401_UNAUTHORIZED,
            detail="当前登录员工不存在",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not current_employee.is_active:
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail="当前账号已停用",
        )
    if current_employee.must_change_password:
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail="请先修改初始密码",
        )

    # CRUD只负责按ID查询；找不到记录时由Service转换成前端可读的404错误。
    rule = await get_discount_rule_by_id(discount_rule_id=discount_rule_id, db=db)
    if rule is None:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail="折扣规则不存在",
        )

    # 详情和列表复用同一个响应组装函数，保证字段和状态计算方式一致。
    return _build_discount_rule_list_item(rule, business_now())


# endregion


# region 获取折扣商品列表
async def get_discount_rule_products_service(
    discount_rule_id: int,
    request: GetDiscountRuleProductsRequest,
    current_employee_id: int,
    db: AsyncSession,
) -> DiscountRuleProductListResponse:
    """验证账号和折扣规则，并组装分页折扣商品列表。"""

    # 第一步：查询接口允许所有正常登录员工使用，但仍需检查账号最新状态。
    current_employee = await get_employee_by_id(employee_id=current_employee_id, db=db)
    if current_employee is None:
        raise HTTPException(
            status_code=http_status.HTTP_401_UNAUTHORIZED,
            detail="当前登录员工不存在",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not current_employee.is_active:
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail="当前账号已停用",
        )
    if current_employee.must_change_password:
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail="请先修改初始密码",
        )

    # 第二步：先确认规则存在，同时取得计算折后价所需的折扣方式和折扣数值。
    rule = await get_discount_rule_by_id(discount_rule_id=discount_rule_id, db=db)
    if rule is None:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail="折扣规则不存在",
        )

    # 第三步：根据筛选条件查询当前页的商品关联。
    offset = (request.page - 1) * request.page_size
    scopes, total = await get_discount_rule_products_list(
        discount_rule_id=discount_rule_id,
        offset=offset,
        page_size=request.page_size,
        keyword=request.keyword,
        category_id=request.category_id,
        db=db,
    )

    # 第四步：把关联对象、商品资料和规则价格合并成前端直接展示的一行数据。
    items: list[DiscountRuleProductItemResponse] = []
    for scope in scopes:
        product = scope.product
        if product is None:
            # 商品外键受数据库约束保护；这里防止异常脏数据导致整个列表接口报错。
            continue
        items.append(
            DiscountRuleProductItemResponse(
                scope_id=scope.id,
                discount_rule_id=discount_rule_id,
                product_id=product.id,
                product_no=product.product_no,
                product_name=product.name,
                department_id=product.department_id,
                department_name=product.department.name,
                category_id=product.category_id,
                category_name=product.category.name,
                original_price=product.sale_price,
                discount_type=rule.discount_type,
                discount_value=rule.discount_value,
                discounted_price=_calculate_discounted_price(
                    original_price=product.sale_price,
                    discount_type=rule.discount_type,
                    discount_value=rule.discount_value,
                ),
                product_status=product.status,
                created_at=scope.created_at,
            )
        )

    return DiscountRuleProductListResponse(
        items=items,
        page=request.page,
        page_size=request.page_size,
        total=total,
        total_pages=(total + request.page_size - 1) // request.page_size,
    )


# endregion


# region 创建折扣规则
async def create_discount_rule_service(
    request: CreateDiscountRuleRequest,
    current_employee_id: int,
    db: AsyncSession,
) -> DiscountRuleListItemResponse:
    """验证员工权限和规则配置，创建折扣规则并记录操作审计。"""

    # 第一步：检查执行创建操作的员工账号。
    current_employee = await get_employee_by_id(employee_id=current_employee_id, db=db)
    if current_employee is None:
        raise HTTPException(
            status_code=http_status.HTTP_401_UNAUTHORIZED,
            detail="当前登录员工不存在",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not current_employee.is_active:
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail="当前账号已停用",
        )
    if current_employee.must_change_password:
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail="请先修改初始密码",
        )
    # 店长可以创建供任意部门使用的折扣规则，因此不限制所属部门。
    if current_employee.role == EmployeeRole.STORE_MANAGER:
        pass
    # 正式员工必须先有明确的所属部门；添加商品时还会继续校验商品部门。
    elif current_employee.role == EmployeeRole.REGULAR_EMPLOYEE:
        if current_employee.department_id is None:
            raise HTTPException(
                status_code=http_status.HTTP_403_FORBIDDEN,
                detail="正式员工未分配所属部门，不能创建折扣规则",
            )
    # 契约工以及以后新增的其他角色都没有折扣管理权限。
    else:
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail="只有店长或正式员工可以创建折扣规则",
        )

    # 第二步：确认规则所属部门存在并且处于启用状态。
    department = await get_department_by_id(department_id=request.department_id, db=db)
    if department is None:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail="所属部门不存在",
        )
    if not department.is_active:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail="所属部门已停用",
        )

    # 正式员工只能为自己的所属部门创建规则；店长可以选择任意启用部门。
    if current_employee.role == EmployeeRole.REGULAR_EMPLOYEE:
        if request.department_id != current_employee.department_id:
            raise HTTPException(
                status_code=http_status.HTTP_403_FORBIDDEN,
                detail="正式员工只能为自己所属部门创建折扣规则",
            )

    # 第三步：提前检查名称重复，向前端返回明确的业务错误。
    same_name_rule = await get_discount_rule_by_name(name=request.name, db=db)
    if same_name_rule is not None:
        raise HTTPException(
            status_code=http_status.HTTP_409_CONFLICT,
            detail="折扣规则名称已存在",
        )

    # 第四步：按折扣方式检查数值。percentage使用0到1之间的小数表示折扣比例。
    if request.discount_type == DiscountType.PERCENTAGE and request.discount_value >= 1:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail="比例折扣必须大于0且小于1，例如0.8表示八折",
        )

    # 第五步：根据执行周期检查需要填写的时间字段，并清理每周执行日。
    weekdays: list[int] | None = None
    now = business_now()
    if request.schedule_type == DiscountScheduleType.ONCE:
        if request.starts_at is None or request.ends_at is None:
            raise HTTPException(
                status_code=http_status.HTTP_400_BAD_REQUEST,
                detail="单次折扣必须填写开始时间和结束时间",
            )
        if request.starts_at >= request.ends_at:
            raise HTTPException(
                status_code=http_status.HTTP_400_BAD_REQUEST,
                detail="单次折扣的结束时间必须晚于开始时间",
            )
        if request.ends_at <= now:
            raise HTTPException(
                status_code=http_status.HTTP_400_BAD_REQUEST,
                detail="单次折扣的结束时间必须晚于当前时间",
            )
        if (
            request.daily_start_time is not None
            or request.daily_end_time is not None
            or request.weekdays is not None
        ):
            raise HTTPException(
                status_code=http_status.HTTP_400_BAD_REQUEST,
                detail="单次折扣不能填写每日执行时间或每周执行日",
            )
    else:
        if request.daily_start_time is None or request.daily_end_time is None:
            raise HTTPException(
                status_code=http_status.HTTP_400_BAD_REQUEST,
                detail="每日或每周折扣必须填写每天的开始时间和结束时间",
            )
        if request.daily_start_time >= request.daily_end_time:
            raise HTTPException(
                status_code=http_status.HTTP_400_BAD_REQUEST,
                detail="每日结束时间必须晚于每日开始时间",
            )
        if request.starts_at is not None or request.ends_at is not None:
            raise HTTPException(
                status_code=http_status.HTTP_400_BAD_REQUEST,
                detail="每日或每周折扣不能填写单次活动开始和结束时间",
            )

        if request.schedule_type == DiscountScheduleType.DAILY:
            if request.weekdays is not None:
                raise HTTPException(
                    status_code=http_status.HTTP_400_BAD_REQUEST,
                    detail="每日折扣不需要填写每周执行日",
                )
        else:
            if not request.weekdays:
                raise HTTPException(
                    status_code=http_status.HTTP_400_BAD_REQUEST,
                    detail="每周折扣至少选择一个执行日",
                )
            if any(day < 1 or day > 7 for day in request.weekdays):
                raise HTTPException(
                    status_code=http_status.HTTP_400_BAD_REQUEST,
                    detail="每周执行日只能使用1至7表示周一至周日",
                )
            # 去除重复星期并按周一至周日排序，保证数据库数据格式统一。
            weekdays = sorted(set(request.weekdays))

    # 第六步：折扣规则和审计记录在同一个事务中写入。
    try:
        created_rule = await create_discount_rule(
            department_id=request.department_id,
            name=request.name,
            discount_type=request.discount_type,
            discount_value=request.discount_value,
            schedule_type=request.schedule_type,
            starts_at=request.starts_at,
            ends_at=request.ends_at,
            daily_start_time=request.daily_start_time,
            daily_end_time=request.daily_end_time,
            weekdays=weekdays,
            is_active=request.is_active,
            created_by=current_employee_id,
            db=db,
        )
        await create_operation_audit_log(
            employee_id=current_employee_id,
            module="discount",
            action="create",
            target_type="discount_rule",
            target_id=created_rule.id,
            before_data=None,
            after_data={
                "department_id": created_rule.department_id,
                "name": created_rule.name,
                "discount_type": created_rule.discount_type,
                "discount_value": created_rule.discount_value,
                "schedule_type": created_rule.schedule_type,
                "starts_at": created_rule.starts_at,
                "ends_at": created_rule.ends_at,
                "daily_start_time": created_rule.daily_start_time,
                "daily_end_time": created_rule.daily_end_time,
                "weekdays": created_rule.weekdays,
                "is_active": created_rule.is_active,
            },
            reason=None,
            db=db,
        )
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=http_status.HTTP_409_CONFLICT,
            detail="折扣规则名称已存在",
        ) from exc

    # 第七步：重新查询以加载创建员工和所属部门关系，并返回最终数据。
    saved_rule = await get_discount_rule_by_id(discount_rule_id=created_rule.id, db=db)
    if saved_rule is None:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail="新创建的折扣规则不存在",
        )
    return _build_discount_rule_list_item(saved_rule, business_now())


# endregion


# region 添加折扣商品
async def add_discount_rule_products_service(
    discount_rule_id: int,
    request: AddDiscountRuleProductsRequest,
    current_employee_id: int,
    db: AsyncSession,
) -> AddDiscountRuleProductsResponse:
    """验证账号、商品和部门权限，并为现有规则批量添加商品。"""

    # 第一步：验证当前登录账号仍然可以执行数据变更操作。
    current_employee = await get_employee_by_id(employee_id=current_employee_id, db=db)
    if current_employee is None:
        raise HTTPException(
            status_code=http_status.HTTP_401_UNAUTHORIZED,
            detail="当前登录员工不存在",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not current_employee.is_active:
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail="当前账号已停用",
        )
    if current_employee.must_change_password:
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail="请先修改初始密码",
        )
    if current_employee.role not in (
        EmployeeRole.STORE_MANAGER,
        EmployeeRole.REGULAR_EMPLOYEE,
    ):
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail="只有店长或正式员工可以添加折扣商品",
        )
    if (
        current_employee.role == EmployeeRole.REGULAR_EMPLOYEE
        and current_employee.department_id is None
    ):
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail="正式员工未分配所属部门，不能添加折扣商品",
        )

    # 第二步：确认准备添加商品的折扣规则真实存在。
    rule = await get_discount_rule_by_id(discount_rule_id=discount_rule_id, db=db)
    if rule is None:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail="折扣规则不存在",
        )

    # 正式员工只能管理自己部门的折扣规则。
    if current_employee.role == EmployeeRole.REGULAR_EMPLOYEE:
        if rule.department_id != current_employee.department_id:
            raise HTTPException(
                status_code=http_status.HTTP_403_FORBIDDEN,
                detail="正式员工只能管理自己所属部门的折扣规则",
            )

    # 第三步：使用普通循环去除重复ID，避免为同一个商品创建两条关联。
    product_ids: list[int] = []
    for product_id in request.product_ids:
        if product_id not in product_ids:
            product_ids.append(product_id)
    product_ids.sort()

    # 查询商品后，把数据库实际找到的ID保存到集合中，便于逐个检查。
    products = await get_discount_products_by_ids(product_ids=product_ids, db=db)
    found_product_ids: set[int] = set()
    for product in products:
        found_product_ids.add(product.id)

    # 保存数据库中不存在的商品ID。
    missing_product_ids: list[int] = []
    for product_id in product_ids:
        if product_id not in found_product_ids:
            missing_product_ids.append(product_id)

    if missing_product_ids:
        missing_id_texts: list[str] = []
        for product_id in missing_product_ids:
            missing_id_texts.append(str(product_id))
        missing_text = "、".join(missing_id_texts)
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail=f"以下商品不存在：{missing_text}",
        )

    # 第四步：无论操作者是不是店长，商品都必须属于规则指定的部门。
    other_department_product_ids: list[int] = []
    for product in products:
        if product.department_id != rule.department_id:
            other_department_product_ids.append(product.id)

    if other_department_product_ids:
        product_id_texts: list[str] = []
        for product_id in other_department_product_ids:
            product_id_texts.append(str(product_id))
        product_text = "、".join(product_id_texts)
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail=f"折扣商品必须属于规则指定的部门：{product_text}",
        )

    # 第五步：已经关联的商品不允许再次添加，避免唯一约束错误难以理解。
    existing_product_ids = await get_existing_discount_product_ids(
        discount_rule_id=discount_rule_id,
        product_ids=product_ids,
        db=db,
    )
    if existing_product_ids:
        existing_id_texts: list[str] = []
        for product_id in sorted(existing_product_ids):
            existing_id_texts.append(str(product_id))
        existing_text = "、".join(existing_id_texts)
        raise HTTPException(
            status_code=http_status.HTTP_409_CONFLICT,
            detail=f"以下商品已经加入该折扣规则：{existing_text}",
        )

    # 第六步：商品关联与审计记录共用一个事务，任何一步失败都会全部回滚。
    try:
        await create_discount_rule_product_scopes(
            discount_rule_id=discount_rule_id,
            product_ids=product_ids,
            db=db,
        )
        await create_operation_audit_log(
            employee_id=current_employee_id,
            module="discount",
            action="add_products",
            target_type="discount_rule",
            target_id=discount_rule_id,
            before_data=None,
            after_data={"product_ids": product_ids},
            reason=None,
            db=db,
        )
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=http_status.HTTP_409_CONFLICT,
            detail="部分商品已经加入该折扣规则",
        ) from exc

    return AddDiscountRuleProductsResponse(
        discount_rule_id=discount_rule_id,
        product_ids=product_ids,
    )


# endregion


# region 删除单个折扣商品
async def delete_discount_rule_product_service(
    discount_rule_id: int,
    product_id: int,
    current_employee_id: int,
    db: AsyncSession,
) -> DeleteDiscountRuleProductsResponse:
    """验证账号和部门权限，并删除一条折扣商品关联。"""

    # 第一步：验证当前登录员工和账号状态。
    current_employee = await get_employee_by_id(employee_id=current_employee_id, db=db)
    if current_employee is None:
        raise HTTPException(
            status_code=http_status.HTTP_401_UNAUTHORIZED,
            detail="当前登录员工不存在",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not current_employee.is_active:
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail="当前账号已停用",
        )
    if current_employee.must_change_password:
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail="请先修改初始密码",
        )
    if current_employee.role not in (
        EmployeeRole.STORE_MANAGER,
        EmployeeRole.REGULAR_EMPLOYEE,
    ):
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail="只有店长或正式员工可以删除折扣商品",
        )

    # 第二步：确认折扣规则存在。
    rule = await get_discount_rule_by_id(discount_rule_id=discount_rule_id, db=db)
    if rule is None:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail="折扣规则不存在",
        )

    # 正式员工只能删除自己部门规则中的商品关联。
    if current_employee.role == EmployeeRole.REGULAR_EMPLOYEE:
        if rule.department_id != current_employee.department_id:
            raise HTTPException(
                status_code=http_status.HTTP_403_FORBIDDEN,
                detail="正式员工只能管理自己所属部门的折扣规则",
            )

    # 第三步：查询这条规则和商品之间的关联。
    scope = await get_discount_rule_product_scope(
        discount_rule_id=discount_rule_id,
        product_id=product_id,
        db=db,
    )
    if scope is None or scope.product is None:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail="该商品没有加入此折扣规则",
        )

    # 第四步：正式员工只能删除自己所属部门的折扣商品。
    if current_employee.role == EmployeeRole.REGULAR_EMPLOYEE:
        if current_employee.department_id is None:
            raise HTTPException(
                status_code=http_status.HTTP_403_FORBIDDEN,
                detail="正式员工未分配所属部门，不能删除折扣商品",
            )
        if scope.product.department_id != current_employee.department_id:
            raise HTTPException(
                status_code=http_status.HTTP_403_FORBIDDEN,
                detail="正式员工只能删除自己所属部门的折扣商品",
            )

    # 第五步：删除关联并记录审计。商品表和折扣规则表都不会被删除。
    try:
        await delete_discount_rule_product_scopes(scopes=[scope], db=db)
        await create_operation_audit_log(
            employee_id=current_employee_id,
            module="discount",
            action="delete_product",
            target_type="discount_rule_scope",
            target_id=scope.id,
            before_data={
                "discount_rule_id": discount_rule_id,
                "product_id": product_id,
                "product_name": scope.product.name,
            },
            after_data=None,
            reason=None,
            db=db,
        )
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=http_status.HTTP_409_CONFLICT,
            detail="折扣商品删除失败，请稍后重试",
        ) from exc

    return DeleteDiscountRuleProductsResponse(
        discount_rule_id=discount_rule_id,
        deleted_count=1,
        deleted_product_ids=[product_id],
    )


# endregion


# region 删除全部折扣商品
async def delete_all_discount_rule_products_service(
    discount_rule_id: int,
    current_employee_id: int,
    db: AsyncSession,
) -> DeleteDiscountRuleProductsResponse:
    """删除规则下当前员工有权管理的全部商品关联。"""

    # 第一步：验证当前登录员工和账号状态。
    current_employee = await get_employee_by_id(employee_id=current_employee_id, db=db)
    if current_employee is None:
        raise HTTPException(
            status_code=http_status.HTTP_401_UNAUTHORIZED,
            detail="当前登录员工不存在",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not current_employee.is_active:
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail="当前账号已停用",
        )
    if current_employee.must_change_password:
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail="请先修改初始密码",
        )
    if current_employee.role not in (
        EmployeeRole.STORE_MANAGER,
        EmployeeRole.REGULAR_EMPLOYEE,
    ):
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail="只有店长或正式员工可以删除折扣商品",
        )

    # 第二步：确认折扣规则存在。
    rule = await get_discount_rule_by_id(discount_rule_id=discount_rule_id, db=db)
    if rule is None:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail="折扣规则不存在",
        )

    # 正式员工只能清空自己部门的折扣规则。
    if current_employee.role == EmployeeRole.REGULAR_EMPLOYEE:
        if rule.department_id != current_employee.department_id:
            raise HTTPException(
                status_code=http_status.HTTP_403_FORBIDDEN,
                detail="正式员工只能管理自己所属部门的折扣规则",
            )

    # 第三步：店长查询全部商品；正式员工只查询自己部门的商品。
    department_id: int | None = None
    if current_employee.role == EmployeeRole.REGULAR_EMPLOYEE:
        if current_employee.department_id is None:
            raise HTTPException(
                status_code=http_status.HTTP_403_FORBIDDEN,
                detail="正式员工未分配所属部门，不能删除折扣商品",
            )
        department_id = current_employee.department_id

    scopes = await get_discount_rule_product_scopes_for_delete(
        discount_rule_id=discount_rule_id,
        department_id=department_id,
        db=db,
    )

    # 没有符合权限范围的商品时直接返回0，重复点击删除也不会报错。
    if not scopes:
        return DeleteDiscountRuleProductsResponse(
            discount_rule_id=discount_rule_id,
            deleted_count=0,
            deleted_product_ids=[],
        )

    # 使用普通循环收集商品ID，便于逐步理解每条关联的处理过程。
    deleted_product_ids: list[int] = []
    for scope in scopes:
        if scope.product_id is not None:
            deleted_product_ids.append(scope.product_id)

    # 第四步：删除查询到的关联，并把本次删除的商品ID写入审计记录。
    try:
        await delete_discount_rule_product_scopes(scopes=scopes, db=db)
        await create_operation_audit_log(
            employee_id=current_employee_id,
            module="discount",
            action="delete_all_products",
            target_type="discount_rule",
            target_id=discount_rule_id,
            before_data={"product_ids": deleted_product_ids},
            after_data=None,
            reason=None,
            db=db,
        )
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=http_status.HTTP_409_CONFLICT,
            detail="折扣商品批量删除失败，请稍后重试",
        ) from exc

    return DeleteDiscountRuleProductsResponse(
        discount_rule_id=discount_rule_id,
        deleted_count=len(deleted_product_ids),
        deleted_product_ids=deleted_product_ids,
    )


# endregion


# region 修改折扣规则资料
async def update_discount_rule_service(
    discount_rule_id: int,
    request: UpdateDiscountRuleRequest,
    current_employee_id: int,
    db: AsyncSession,
) -> DiscountRuleListItemResponse:
    """验证账号、部门权限和规则配置，并修改折扣规则资料。"""

    # 第一步：检查当前登录员工是否仍然可以执行数据修改操作。
    current_employee = await get_employee_by_id(employee_id=current_employee_id, db=db)
    if current_employee is None:
        raise HTTPException(
            status_code=http_status.HTTP_401_UNAUTHORIZED,
            detail="当前登录员工不存在",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not current_employee.is_active:
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail="当前账号已停用",
        )
    if current_employee.must_change_password:
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail="请先修改初始密码",
        )
    if current_employee.role not in (
        EmployeeRole.STORE_MANAGER,
        EmployeeRole.REGULAR_EMPLOYEE,
    ):
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail="只有店长或正式员工可以修改折扣规则",
        )

    # 第二步：查询要修改的规则，并限制正式员工只能管理本部门规则。
    rule = await get_discount_rule_by_id(discount_rule_id=discount_rule_id, db=db)
    if rule is None:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail="折扣规则不存在",
        )
    if current_employee.role == EmployeeRole.REGULAR_EMPLOYEE:
        if rule.department_id != current_employee.department_id:
            raise HTTPException(
                status_code=http_status.HTTP_403_FORBIDDEN,
                detail="正式员工只能修改自己所属部门的折扣规则",
            )

    # exclude_unset=True只保留前端实际传入的字段；reason只写入审计表，不更新规则表。
    requested_data = request.model_dump(exclude_unset=True, exclude={"reason"})
    if not requested_data:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail="至少传入一个需要修改的字段",
        )

    # 第三步：不允许把规则的必填配置显式修改为null。
    required_field_names = (
        "name",
        "discount_type",
        "discount_value",
        "schedule_type",
    )
    for field_name in required_field_names:
        if field_name in requested_data and requested_data[field_name] is None:
            raise HTTPException(
                status_code=http_status.HTTP_400_BAD_REQUEST,
                detail="规则名称、折扣方式、折扣数值和执行周期不能设置为空",
            )

    # 修改名称时排除规则自身，防止保留原名称被误判为重复。
    new_name = requested_data.get("name")
    if isinstance(new_name, str) and new_name != rule.name:
        same_name_rule = await get_discount_rule_by_name(
            name=new_name,
            excluded_discount_rule_id=rule.id,
            db=db,
        )
        if same_name_rule is not None:
            raise HTTPException(
                status_code=http_status.HTTP_409_CONFLICT,
                detail="折扣规则名称已存在",
            )

    # 第四步：把未修改的折扣字段沿用旧值，再校验组合后的折扣配置。
    new_discount_type = rule.discount_type
    if request.discount_type is not None:
        new_discount_type = request.discount_type

    new_discount_value = rule.discount_value
    if request.discount_value is not None:
        new_discount_value = request.discount_value

    if new_discount_type == DiscountType.PERCENTAGE and new_discount_value >= 1:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail="比例折扣必须大于0且小于1，例如0.8表示八折",
        )

    # 第五步：只要修改了执行周期相关字段，就重新整理并校验整套时间配置。
    schedule_field_names = (
        "schedule_type",
        "starts_at",
        "ends_at",
        "daily_start_time",
        "daily_end_time",
        "weekdays",
    )
    schedule_was_changed = False
    for field_name in schedule_field_names:
        if field_name in requested_data:
            schedule_was_changed = True
            break

    if schedule_was_changed:
        new_schedule_type = rule.schedule_type
        if request.schedule_type is not None:
            new_schedule_type = request.schedule_type

        if new_schedule_type == DiscountScheduleType.ONCE:
            new_starts_at = rule.starts_at
            if "starts_at" in requested_data:
                new_starts_at = request.starts_at

            new_ends_at = rule.ends_at
            if "ends_at" in requested_data:
                new_ends_at = request.ends_at

            if new_starts_at is None or new_ends_at is None:
                raise HTTPException(
                    status_code=http_status.HTTP_400_BAD_REQUEST,
                    detail="单次折扣必须填写开始时间和结束时间",
                )
            if new_starts_at >= new_ends_at:
                raise HTTPException(
                    status_code=http_status.HTTP_400_BAD_REQUEST,
                    detail="单次折扣的结束时间必须晚于开始时间",
                )
            if new_ends_at <= business_now():
                raise HTTPException(
                    status_code=http_status.HTTP_400_BAD_REQUEST,
                    detail="单次折扣的结束时间必须晚于当前时间",
                )

            # 单次规则只保留完整日期时间，自动清空循环规则才使用的字段。
            requested_data["schedule_type"] = new_schedule_type
            requested_data["starts_at"] = new_starts_at
            requested_data["ends_at"] = new_ends_at
            requested_data["daily_start_time"] = None
            requested_data["daily_end_time"] = None
            requested_data["weekdays"] = None
        else:
            new_daily_start_time = rule.daily_start_time
            if "daily_start_time" in requested_data:
                new_daily_start_time = request.daily_start_time

            new_daily_end_time = rule.daily_end_time
            if "daily_end_time" in requested_data:
                new_daily_end_time = request.daily_end_time

            if new_daily_start_time is None or new_daily_end_time is None:
                raise HTTPException(
                    status_code=http_status.HTTP_400_BAD_REQUEST,
                    detail="每日或每周折扣必须填写每天的开始时间和结束时间",
                )
            if new_daily_start_time >= new_daily_end_time:
                raise HTTPException(
                    status_code=http_status.HTTP_400_BAD_REQUEST,
                    detail="每日结束时间必须晚于每日开始时间",
                )

            normalized_weekdays: list[int] | None = None
            if new_schedule_type == DiscountScheduleType.WEEKLY:
                new_weekdays = rule.weekdays
                if "weekdays" in requested_data:
                    new_weekdays = request.weekdays
                if not new_weekdays:
                    raise HTTPException(
                        status_code=http_status.HTTP_400_BAD_REQUEST,
                        detail="每周折扣至少选择一个执行日",
                    )

                # 使用普通循环检查范围并去重，1至7分别代表周一至周日。
                normalized_weekdays = []
                for weekday in new_weekdays:
                    if weekday < 1 or weekday > 7:
                        raise HTTPException(
                            status_code=http_status.HTTP_400_BAD_REQUEST,
                            detail="每周执行日只能使用1至7表示周一至周日",
                        )
                    if weekday not in normalized_weekdays:
                        normalized_weekdays.append(weekday)
                normalized_weekdays.sort()

            # 循环规则只保留每天的执行时段；每日规则不需要weekdays。
            requested_data["schedule_type"] = new_schedule_type
            requested_data["starts_at"] = None
            requested_data["ends_at"] = None
            requested_data["daily_start_time"] = new_daily_start_time
            requested_data["daily_end_time"] = new_daily_end_time
            requested_data["weekdays"] = normalized_weekdays

    # 第六步：只保存真正发生变化的字段，并记录每个字段修改前后的值。
    update_data: dict[str, object] = {}
    before_data: dict[str, object] = {}
    for field_name, new_value in requested_data.items():
        old_value = getattr(rule, field_name)
        if old_value != new_value:
            update_data[field_name] = new_value
            before_data[field_name] = old_value

    # 前端提交的值与数据库完全相同时直接返回，不产生空审计记录。
    if not update_data:
        return _build_discount_rule_list_item(rule, business_now())

    # 第七步：更新规则和写入审计记录共用一个事务，任一步失败都会回滚。
    try:
        await update_discount_rule(
            discount_rule_id=discount_rule_id,
            update_data=update_data,
            db=db,
        )
        await create_operation_audit_log(
            employee_id=current_employee_id,
            module="discount",
            action="update",
            target_type="discount_rule",
            target_id=discount_rule_id,
            before_data=before_data,
            after_data=update_data,
            reason=request.reason,
            db=db,
        )
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=http_status.HTTP_409_CONFLICT,
            detail="折扣规则修改失败，名称可能已经存在",
        ) from exc

    # 第八步：重新查询，以取得最新更新时间及已加载的员工、部门关系。
    updated_rule = await get_discount_rule_by_id(discount_rule_id=discount_rule_id, db=db)
    if updated_rule is None:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail="修改后的折扣规则不存在",
        )
    return _build_discount_rule_list_item(updated_rule, business_now())


# endregion


# region 修改折扣规则状态
async def update_discount_rule_status_service(
    discount_rule_id: int,
    request: UpdateDiscountRuleStatusRequest,
    current_employee_id: int,
    db: AsyncSession,
) -> DiscountRuleListItemResponse:
    """验证账号和部门权限，并开启或关闭折扣规则。"""

    # 第一步：验证当前登录员工和账号状态。
    current_employee = await get_employee_by_id(employee_id=current_employee_id, db=db)
    if current_employee is None:
        raise HTTPException(
            status_code=http_status.HTTP_401_UNAUTHORIZED,
            detail="当前登录员工不存在",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not current_employee.is_active:
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail="当前账号已停用",
        )
    if current_employee.must_change_password:
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail="请先修改初始密码",
        )
    if current_employee.role not in (
        EmployeeRole.STORE_MANAGER,
        EmployeeRole.REGULAR_EMPLOYEE,
    ):
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail="只有店长或正式员工可以开启或关闭折扣规则",
        )

    # 第二步：查询规则并检查正式员工的部门权限。
    rule = await get_discount_rule_by_id(discount_rule_id=discount_rule_id, db=db)
    if rule is None:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail="折扣规则不存在",
        )
    if current_employee.role == EmployeeRole.REGULAR_EMPLOYEE:
        if rule.department_id != current_employee.department_id:
            raise HTTPException(
                status_code=http_status.HTTP_403_FORBIDDEN,
                detail="正式员工只能修改自己所属部门的折扣规则",
            )

    # 请求状态与数据库相同时不执行更新，也不生成没有实际变化的审计记录。
    if rule.is_active == request.is_active:
        return _build_discount_rule_list_item(rule, business_now())

    # 第三步：修改状态并记录修改前后的值，然后统一提交事务。
    try:
        await update_discount_rule_status(
            discount_rule_id=discount_rule_id,
            is_active=request.is_active,
            db=db,
        )
        await create_operation_audit_log(
            employee_id=current_employee_id,
            module="discount",
            action="update_status",
            target_type="discount_rule",
            target_id=discount_rule_id,
            before_data={"is_active": rule.is_active},
            after_data={"is_active": request.is_active},
            reason=request.reason,
            db=db,
        )
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=http_status.HTTP_409_CONFLICT,
            detail="折扣规则状态修改失败，请稍后重试",
        ) from exc

    # 第四步：重新查询，取得数据库中的最新状态和更新时间。
    updated_rule = await get_discount_rule_by_id(discount_rule_id=discount_rule_id, db=db)
    if updated_rule is None:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail="修改后的折扣规则不存在",
        )
    return _build_discount_rule_list_item(updated_rule, business_now())


# endregion


# region 删除单个折扣规则
async def delete_discount_rule_service(
    discount_rule_id: int,
    current_employee_id: int,
    db: AsyncSession,
) -> DeleteDiscountRulesResponse:
    """验证账号和部门权限，并删除指定折扣规则。"""

    # 第一步：验证当前登录员工和账号状态。
    current_employee = await get_employee_by_id(employee_id=current_employee_id, db=db)
    if current_employee is None:
        raise HTTPException(
            status_code=http_status.HTTP_401_UNAUTHORIZED,
            detail="当前登录员工不存在",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not current_employee.is_active:
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail="当前账号已停用",
        )
    if current_employee.must_change_password:
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail="请先修改初始密码",
        )
    if current_employee.role not in (
        EmployeeRole.STORE_MANAGER,
        EmployeeRole.REGULAR_EMPLOYEE,
    ):
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail="只有店长或正式员工可以删除折扣规则",
        )

    # 第二步：查询规则并检查正式员工的部门权限。
    rule = await get_discount_rule_by_id(discount_rule_id=discount_rule_id, db=db)
    if rule is None:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail="折扣规则不存在",
        )
    if current_employee.role == EmployeeRole.REGULAR_EMPLOYEE:
        if rule.department_id != current_employee.department_id:
            raise HTTPException(
                status_code=http_status.HTTP_403_FORBIDDEN,
                detail="正式员工只能删除自己所属部门的折扣规则",
            )

    # 第三步：记录删除前的数据，删除规则，并统一提交事务。
    try:
        await create_operation_audit_log(
            employee_id=current_employee_id,
            module="discount",
            action="delete",
            target_type="discount_rule",
            target_id=rule.id,
            before_data={
                "department_id": rule.department_id,
                "name": rule.name,
                "discount_type": rule.discount_type,
                "discount_value": rule.discount_value,
                "schedule_type": rule.schedule_type,
                "is_active": rule.is_active,
            },
            after_data=None,
            reason=None,
            db=db,
        )
        await delete_discount_rules(rule_ids=[rule.id], db=db)
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=http_status.HTTP_409_CONFLICT,
            detail="折扣规则删除失败，请稍后重试",
        ) from exc

    return DeleteDiscountRulesResponse(
        deleted_count=1,
        deleted_rule_ids=[rule.id],
    )


# endregion


# region 一键清空折扣规则
async def clear_discount_rules_service(
    current_employee_id: int,
    db: AsyncSession,
) -> DeleteDiscountRulesResponse:
    """清空当前员工权限范围内的折扣规则。"""

    # 第一步：验证当前登录员工和账号状态。
    current_employee = await get_employee_by_id(employee_id=current_employee_id, db=db)
    if current_employee is None:
        raise HTTPException(
            status_code=http_status.HTTP_401_UNAUTHORIZED,
            detail="当前登录员工不存在",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not current_employee.is_active:
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail="当前账号已停用",
        )
    if current_employee.must_change_password:
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail="请先修改初始密码",
        )
    if current_employee.role not in (
        EmployeeRole.STORE_MANAGER,
        EmployeeRole.REGULAR_EMPLOYEE,
    ):
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail="只有店长或正式员工可以清空折扣规则",
        )

    # 第二步：店长查询全部规则，正式员工只查询自己部门的规则。
    department_id: int | None = None
    if current_employee.role == EmployeeRole.REGULAR_EMPLOYEE:
        if current_employee.department_id is None:
            raise HTTPException(
                status_code=http_status.HTTP_403_FORBIDDEN,
                detail="正式员工未分配所属部门，不能清空折扣规则",
            )
        department_id = current_employee.department_id

    rules = await get_discount_rules_for_delete(department_id=department_id, db=db)

    # 当前权限范围内没有规则时直接返回0，使重复点击清空保持安全。
    if not rules:
        return DeleteDiscountRulesResponse(
            deleted_count=0,
            deleted_rule_ids=[],
        )

    # 使用普通循环收集规则ID，避免使用不易理解的列表推导式。
    deleted_rule_ids: list[int] = []
    for rule in rules:
        deleted_rule_ids.append(rule.id)

    # 第三步：每条规则分别记录审计，然后一次性删除并提交。
    try:
        for rule in rules:
            await create_operation_audit_log(
                employee_id=current_employee_id,
                module="discount",
                action="delete",
                target_type="discount_rule",
                target_id=rule.id,
                before_data={
                    "department_id": rule.department_id,
                    "name": rule.name,
                    "discount_type": rule.discount_type,
                    "discount_value": rule.discount_value,
                    "schedule_type": rule.schedule_type,
                    "is_active": rule.is_active,
                },
                after_data=None,
                reason=None,
                db=db,
            )

        await delete_discount_rules(rule_ids=deleted_rule_ids, db=db)
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=http_status.HTTP_409_CONFLICT,
            detail="折扣规则清空失败，请稍后重试",
        ) from exc

    return DeleteDiscountRulesResponse(
        deleted_count=len(deleted_rule_ids),
        deleted_rule_ids=deleted_rule_ids,
    )


# endregion


__all__ = [
    "calculate_discount_rule_status",
    "add_discount_rule_products_service",
    "clear_discount_rules_service",
    "create_discount_rule_service",
    "delete_all_discount_rule_products_service",
    "delete_discount_rule_product_service",
    "delete_discount_rule_service",
    "get_discount_rule_detail_service",
    "get_discount_rule_list_service",
    "get_discount_rule_products_service",
    "get_product_discount_prices",
    "ProductDiscountPrice",
    "update_discount_rule_service",
    "update_discount_rule_status_service",
]
