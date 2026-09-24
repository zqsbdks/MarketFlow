"""折扣规则与适用范围业务逻辑。"""

from datetime import datetime

from fastapi import HTTPException
from fastapi import status as http_status
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.auth import get_employee_by_id
from app.crud.discount_rule import get_discount_rule_by_id, get_discount_rules_list
from app.models.discount_rule import DiscountRule
from app.models.enums import (
    DiscountComputedStatus,
    DiscountScheduleType,
    DiscountType,
)
from app.schemas.discount_rule_responses import (
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
        start_stock_threshold=rule.start_stock_threshold,
        end_stock_threshold=rule.end_stock_threshold,
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


# region 折扣适用范围业务逻辑
# 后续添加：目标存在性、部门权限和重复范围校验函数。
# endregion


__all__ = [
    "calculate_discount_rule_status",
    "get_discount_rule_detail_service",
    "get_discount_rule_list_service",
]
