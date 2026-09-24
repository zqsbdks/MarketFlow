"""折扣规则与适用范围数据库访问函数。"""

from datetime import datetime

from sqlalchemy import and_, func, not_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.sql.elements import ColumnElement

from app.models.discount_rule import DiscountRule
from app.models.enums import (
    DiscountComputedStatus,
    DiscountScheduleType,
    DiscountType,
)


# region 折扣规则动态状态查询条件
def _get_active_schedule_condition(now: datetime) -> ColumnElement[bool]:
    """生成“当前处于规则执行时间内”的SQL查询条件。"""

    # 数据库存储的循环时间不包含日期，因此只取当前时、分、秒进行比较。
    current_time = now.time().replace(microsecond=0)

    # 单次规则：当前时间必须大于等于开始时间，并且小于结束时间。
    once_is_active = and_(
        DiscountRule.schedule_type == DiscountScheduleType.ONCE,
        DiscountRule.starts_at <= now,
        DiscountRule.ends_at > now,
    )

    # 每日规则：每天只要当前时间处于设置的时间段内，就属于正在执行。
    daily_is_active = and_(
        DiscountRule.schedule_type == DiscountScheduleType.DAILY,
        DiscountRule.daily_start_time <= current_time,
        DiscountRule.daily_end_time > current_time,
    )

    # 每周规则：除了满足每日时间段，还要求weekdays数组包含今天的星期数字。
    # isoweekday使用1至7表示周一至周日，正好与数据库weekdays字段约定一致。
    weekly_is_active = and_(
        DiscountRule.schedule_type == DiscountScheduleType.WEEKLY,
        func.coalesce(
            func.json_contains(DiscountRule.weekdays, str(now.isoweekday())),
            0,
        )
        == 1,
        DiscountRule.daily_start_time <= current_time,
        DiscountRule.daily_end_time > current_time,
    )

    # 三种执行周期只要满足其中一种，就表示规则当前处于执行时间内。
    return or_(once_is_active, daily_is_active, weekly_is_active)


def _get_computed_status_condition(
    computed_status: DiscountComputedStatus,
    now: datetime,
) -> ColumnElement[bool]:
    """把前端选择的动态状态转换成数据库能够执行的SQL条件。"""

    active_schedule = _get_active_schedule_condition(now)
    ended_once_rule = and_(
        DiscountRule.schedule_type == DiscountScheduleType.ONCE,
        DiscountRule.ends_at <= now,
    )

    if computed_status == DiscountComputedStatus.DISABLED:
        # 人工开关关闭后，不再考虑时间，统一显示为已停用。
        return DiscountRule.is_active.is_(False)
    if computed_status == DiscountComputedStatus.ACTIVE:
        # 正在生效必须同时满足：人工开关已开启，并且当前处于执行时间内。
        return and_(DiscountRule.is_active.is_(True), active_schedule)
    if computed_status == DiscountComputedStatus.ENDED:
        # 只有单次活动会永久结束；每日和每周活动离开时段后属于待生效。
        return and_(DiscountRule.is_active.is_(True), ended_once_rule)

    # 待生效包括未来才开始的单次活动，以及当前不在执行时段的循环活动。
    # 已经结束的单次活动必须排除，否则它也会满足“不在执行时段”。
    return and_(
        DiscountRule.is_active.is_(True),
        not_(active_schedule),
        not_(ended_once_rule),
    )


# endregion


# region 获取折扣规则列表
async def get_discount_rules_list(
    offset: int,
    page_size: int,
    keyword: str | None,
    discount_type: DiscountType | None,
    schedule_type: DiscountScheduleType | None,
    is_active: bool | None,
    computed_status: DiscountComputedStatus | None,
    now: datetime,
    db: AsyncSession,
) -> tuple[list[DiscountRule], int]:
    """按筛选条件分页查询折扣规则，并返回符合条件的总条数。"""

    conditions: list[ColumnElement[bool]] = []

    # 每个参数都允许不传；只有前端实际传入时，才添加对应查询条件。
    if keyword is not None:
        conditions.append(DiscountRule.name.ilike(f"%{keyword}%"))
    if discount_type is not None:
        conditions.append(DiscountRule.discount_type == discount_type)
    if schedule_type is not None:
        conditions.append(DiscountRule.schedule_type == schedule_type)
    if is_active is not None:
        conditions.append(DiscountRule.is_active.is_(is_active))
    if computed_status is not None:
        conditions.append(_get_computed_status_condition(computed_status, now))

    # selectinload提前加载创建员工，Service读取员工姓名时不会再次访问数据库。
    list_statement = (
        select(DiscountRule)
        .options(selectinload(DiscountRule.creator))
        .where(*conditions)
        .order_by(DiscountRule.id.desc())
        .offset(offset)
        .limit(page_size)
    )
    count_statement = select(func.count(DiscountRule.id)).where(*conditions)

    total = int(await db.scalar(count_statement) or 0)
    result = await db.scalars(list_statement)
    return list(result.all()), total


# endregion


# region 获取折扣规则详情
async def get_discount_rule_by_id(
    discount_rule_id: int,
    db: AsyncSession,
) -> DiscountRule | None:
    """根据规则ID查询一条折扣规则，并提前加载创建员工。"""

    # 详情响应需要显示创建员工姓名，所以查询规则时一并加载creator关系。
    statement = (
        select(DiscountRule)
        .options(selectinload(DiscountRule.creator))
        .where(DiscountRule.id == discount_rule_id)
        # 如果会话中已经存在该对象，仍使用数据库最新值覆盖旧的会话缓存。
        .execution_options(populate_existing=True)
    )
    result = await db.execute(statement)
    return result.scalar_one_or_none()


# endregion


# region 折扣适用范围数据库操作
# 后续添加：范围查询、批量添加和删除函数。
# endregion


__all__ = ["get_discount_rule_by_id", "get_discount_rules_list"]
