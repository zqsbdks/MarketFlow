"""折扣规则动态状态和列表业务测试。"""

from datetime import datetime, time, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.discount_rule import DiscountRule
from app.models.employee import Employee
from app.models.enums import (
    DiscountComputedStatus,
    DiscountScheduleType,
    DiscountType,
    EmployeeRole,
)
from app.schemas.discount_rule_requests import GetDiscountRuleListRequest
from app.services.discount_rule import (
    calculate_discount_rule_status,
    get_discount_rule_detail_service,
    get_discount_rule_list_service,
)


def build_employee() -> Employee:
    """构造已启用且完成初始密码修改的测试员工。"""

    return Employee(
        id=1,
        employee_no="E00001",
        name="测试店长",
        password_hash="test-hash",
        role=EmployeeRole.STORE_MANAGER,
        department_id=None,
        is_active=True,
        must_change_password=False,
    )


def build_once_rule(now: datetime, *, is_active: bool = True) -> DiscountRule:
    """构造一条当前处于执行时间内的单次折扣规则。"""

    rule = DiscountRule(
        id=1,
        name="测试单次折扣",
        discount_type=DiscountType.PERCENTAGE,
        discount_value=Decimal("0.8000"),
        schedule_type=DiscountScheduleType.ONCE,
        starts_at=now - timedelta(hours=1),
        ends_at=now + timedelta(hours=1),
        is_active=is_active,
        created_by=1,
        created_at=now,
        updated_at=now,
    )
    rule.creator = build_employee()
    return rule


def test_calculate_once_rule_statuses() -> None:
    """单次规则应正确区分已停用、待生效、正在生效和已结束。"""

    now = datetime(2026, 9, 21, 19, 30)
    active_rule = build_once_rule(now)
    assert calculate_discount_rule_status(active_rule, now) == DiscountComputedStatus.ACTIVE

    active_rule.is_active = False
    assert calculate_discount_rule_status(active_rule, now) == DiscountComputedStatus.DISABLED

    active_rule.is_active = True
    active_rule.starts_at = now + timedelta(hours=1)
    active_rule.ends_at = now + timedelta(hours=2)
    assert calculate_discount_rule_status(active_rule, now) == DiscountComputedStatus.SCHEDULED

    active_rule.starts_at = now - timedelta(hours=2)
    active_rule.ends_at = now - timedelta(hours=1)
    assert calculate_discount_rule_status(active_rule, now) == DiscountComputedStatus.ENDED


def test_calculate_daily_and_weekly_rule_statuses() -> None:
    """循环规则应同时检查每日时间段和每周执行日。"""

    now = datetime(2026, 9, 21, 19, 30)  # 2026-09-21是星期一。
    rule = build_once_rule(now)
    rule.schedule_type = DiscountScheduleType.DAILY
    rule.starts_at = None
    rule.ends_at = None
    rule.daily_start_time = time(18, 0)
    rule.daily_end_time = time(21, 0)
    assert calculate_discount_rule_status(rule, now) == DiscountComputedStatus.ACTIVE

    rule.schedule_type = DiscountScheduleType.WEEKLY
    rule.weekdays = [1, 3, 5]
    assert calculate_discount_rule_status(rule, now) == DiscountComputedStatus.ACTIVE

    rule.weekdays = [2, 4, 6]
    assert calculate_discount_rule_status(rule, now) == DiscountComputedStatus.SCHEDULED


def test_list_request_rejects_unknown_computed_status() -> None:
    """前端传入未定义的动态状态时，Pydantic应直接拒绝请求。"""

    with pytest.raises(ValidationError):
        GetDiscountRuleListRequest(computed_status="unknown")


async def test_get_discount_rule_list_service_builds_pagination(monkeypatch) -> None:
    """列表Service应验证员工并组装分页数据和创建员工姓名。"""

    employee = build_employee()
    now = datetime.now()
    rule = build_once_rule(now)
    monkeypatch.setattr(
        "app.services.discount_rule.get_employee_by_id",
        AsyncMock(return_value=employee),
    )
    monkeypatch.setattr(
        "app.services.discount_rule.get_discount_rules_list",
        AsyncMock(return_value=([rule], 1)),
    )

    result = await get_discount_rule_list_service(
        page=1,
        page_size=10,
        keyword=None,
        discount_type=None,
        schedule_type=None,
        is_active=None,
        computed_status=DiscountComputedStatus.ACTIVE,
        current_employee_id=employee.id,
        db=AsyncMock(spec=AsyncSession),
    )

    assert result.total == 1
    assert result.total_pages == 1
    assert result.items[0].created_by_name == "测试店长"
    assert result.items[0].computed_status == DiscountComputedStatus.ACTIVE


async def test_get_discount_rule_detail_service_returns_rule(monkeypatch) -> None:
    """详情Service应返回指定规则、创建员工姓名和当前动态状态。"""

    employee = build_employee()
    rule = build_once_rule(datetime.now())
    monkeypatch.setattr(
        "app.services.discount_rule.get_employee_by_id",
        AsyncMock(return_value=employee),
    )
    monkeypatch.setattr(
        "app.services.discount_rule.get_discount_rule_by_id",
        AsyncMock(return_value=rule),
    )

    result = await get_discount_rule_detail_service(
        discount_rule_id=rule.id,
        current_employee_id=employee.id,
        db=AsyncMock(spec=AsyncSession),
    )

    assert result.id == rule.id
    assert result.name == "测试单次折扣"
    assert result.created_by_name == "测试店长"
    assert result.computed_status == DiscountComputedStatus.ACTIVE


async def test_get_discount_rule_detail_service_rejects_missing_rule(monkeypatch) -> None:
    """查询不存在的折扣规则时，Service应返回404错误。"""

    employee = build_employee()
    monkeypatch.setattr(
        "app.services.discount_rule.get_employee_by_id",
        AsyncMock(return_value=employee),
    )
    monkeypatch.setattr(
        "app.services.discount_rule.get_discount_rule_by_id",
        AsyncMock(return_value=None),
    )

    with pytest.raises(HTTPException) as exception_info:
        await get_discount_rule_detail_service(
            discount_rule_id=999,
            current_employee_id=employee.id,
            db=AsyncMock(spec=AsyncSession),
        )

    assert exception_info.value.status_code == 404
