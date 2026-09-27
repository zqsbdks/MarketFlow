"""折扣规则与适用范围业务逻辑。"""

from datetime import datetime

from fastapi import HTTPException
from fastapi import status as http_status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.auth import get_employee_by_id
from app.crud.discount_rule import (
    create_discount_rule,
    create_discount_rule_product_scopes,
    get_discount_products_by_ids,
    get_discount_rule_by_id,
    get_discount_rule_by_name,
    get_discount_rules_list,
    get_existing_discount_product_ids,
)
from app.crud.operation_audit_logs import create_operation_audit_log
from app.models.discount_rule import DiscountRule
from app.models.enums import (
    DiscountComputedStatus,
    DiscountScheduleType,
    DiscountType,
    EmployeeRole,
)
from app.schemas.discount_rule_requests import (
    AddDiscountRuleProductsRequest,
    CreateDiscountRuleRequest,
)
from app.schemas.discount_rule_responses import (
    AddDiscountRuleProductsResponse,
    DiscountRuleListItemResponse,
    DiscountRuleListResponse,
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


# region 获取折扣规则列表
async def get_discount_rule_list_service(
    page: int,
    page_size: int,
    keyword: str | None,
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
    now = datetime.now()
    offset = (page - 1) * page_size
    rules, total = await get_discount_rules_list(
        offset=offset,
        page_size=page_size,
        keyword=keyword,
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
    return _build_discount_rule_list_item(rule, datetime.now())


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

    # 第二步：提前检查名称重复，向前端返回明确的业务错误。
    same_name_rule = await get_discount_rule_by_name(name=request.name, db=db)
    if same_name_rule is not None:
        raise HTTPException(
            status_code=http_status.HTTP_409_CONFLICT,
            detail="折扣规则名称已存在",
        )

    # 第三步：按折扣方式检查数值。percentage使用0到1之间的小数表示折扣比例。
    if request.discount_type == DiscountType.PERCENTAGE and request.discount_value >= 1:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail="比例折扣必须大于0且小于1，例如0.8表示八折",
        )

    # 第四步：根据执行周期检查需要填写的时间字段，并清理每周执行日。
    weekdays: list[int] | None = None
    now = datetime.now()
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

    # 第五步：折扣规则和审计记录在同一个事务中写入。
    try:
        created_rule = await create_discount_rule(
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

    # 第六步：重新查询以加载创建员工关系，并返回数据库中的最终数据。
    saved_rule = await get_discount_rule_by_id(discount_rule_id=created_rule.id, db=db)
    if saved_rule is None:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail="新创建的折扣规则不存在",
        )
    return _build_discount_rule_list_item(saved_rule, datetime.now())


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

    # 第三步：去除重复ID，并确认前端传入的每一个商品都能在数据库中找到。
    product_ids = sorted(set(request.product_ids))
    products = await get_discount_products_by_ids(product_ids=product_ids, db=db)
    found_product_ids = {product.id for product in products}
    missing_product_ids = [
        product_id for product_id in product_ids if product_id not in found_product_ids
    ]
    if missing_product_ids:
        missing_text = "、".join(str(product_id) for product_id in missing_product_ids)
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail=f"以下商品不存在：{missing_text}",
        )

    # 第四步：正式员工只能把自己所属部门的商品加入折扣；店长不受部门限制。
    if current_employee.role == EmployeeRole.REGULAR_EMPLOYEE:
        other_department_product_ids = [
            product.id
            for product in products
            if product.department_id != current_employee.department_id
        ]
        if other_department_product_ids:
            product_text = "、".join(str(product_id) for product_id in other_department_product_ids)
            raise HTTPException(
                status_code=http_status.HTTP_403_FORBIDDEN,
                detail=f"正式员工只能添加自己所属部门的商品：{product_text}",
            )

    # 第五步：已经关联的商品不允许再次添加，避免唯一约束错误难以理解。
    existing_product_ids = await get_existing_discount_product_ids(
        discount_rule_id=discount_rule_id,
        product_ids=product_ids,
        db=db,
    )
    if existing_product_ids:
        existing_text = "、".join(str(product_id) for product_id in sorted(existing_product_ids))
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


__all__ = [
    "calculate_discount_rule_status",
    "add_discount_rule_products_service",
    "create_discount_rule_service",
    "get_discount_rule_detail_service",
    "get_discount_rule_list_service",
]
