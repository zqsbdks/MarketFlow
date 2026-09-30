"""折扣规则动态状态和列表业务测试。"""

from datetime import datetime, time, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.category import Category
from app.models.department import Department
from app.models.discount_rule import DiscountRule
from app.models.discount_rule_scope import DiscountRuleScope
from app.models.employee import Employee
from app.models.enums import (
    DiscountComputedStatus,
    DiscountScheduleType,
    DiscountScopeType,
    DiscountType,
    EmployeeRole,
    ProductStatus,
)
from app.models.product import Product
from app.schemas.discount_rule_requests import (
    AddDiscountRuleProductsRequest,
    CreateDiscountRuleRequest,
    GetDiscountRuleListRequest,
    GetDiscountRuleProductsRequest,
    UpdateDiscountRuleRequest,
    UpdateDiscountRuleStatusRequest,
)
from app.services.discount_rule import (
    add_discount_rule_products_service,
    calculate_discount_rule_status,
    clear_discount_rules_service,
    create_discount_rule_service,
    delete_all_discount_rule_products_service,
    delete_discount_rule_product_service,
    delete_discount_rule_service,
    get_discount_rule_detail_service,
    get_discount_rule_list_service,
    get_discount_rule_products_service,
    get_product_discount_prices,
    update_discount_rule_service,
    update_discount_rule_status_service,
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


def build_product(*, product_id: int = 1, department_id: int = 1) -> Product:
    """构造用于折扣商品部门权限测试的正式商品。"""

    return Product(id=product_id, department_id=department_id)


def build_department(*, department_id: int = 1) -> Department:
    """构造折扣规则所属的启用部门。"""

    return Department(
        id=department_id,
        code=f"D{department_id:02d}",
        name=f"测试部门{department_id}",
        is_active=True,
    )


def build_regular_employee(*, department_id: int | None = 1) -> Employee:
    """构造已启用的正式员工，可通过department_id模拟是否已分配部门。"""

    return Employee(
        id=2,
        employee_no="E00002",
        name="测试正式员工",
        password_hash="test-hash",
        role=EmployeeRole.REGULAR_EMPLOYEE,
        department_id=department_id,
        is_active=True,
        must_change_password=False,
    )


def build_once_rule(now: datetime, *, is_active: bool = True) -> DiscountRule:
    """构造一条当前处于执行时间内的单次折扣规则。"""

    rule = DiscountRule(
        id=1,
        department_id=1,
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
    rule.department = build_department()
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
        department_id=None,
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


async def test_manager_can_create_daily_discount_rule(monkeypatch) -> None:
    """店长可以创建通过时间校验的每日折扣规则并写入审计记录。"""

    employee = build_employee()
    now = datetime.now()
    rule = build_once_rule(now)
    rule.name = "晚间生鲜八折"
    rule.schedule_type = DiscountScheduleType.DAILY
    rule.starts_at = None
    rule.ends_at = None
    rule.daily_start_time = time(18, 0)
    rule.daily_end_time = time(21, 0)

    create_record = AsyncMock(return_value=rule)
    audit_record = AsyncMock()
    monkeypatch.setattr(
        "app.services.discount_rule.get_employee_by_id",
        AsyncMock(return_value=employee),
    )
    monkeypatch.setattr(
        "app.services.discount_rule.get_department_by_id",
        AsyncMock(return_value=build_department()),
    )
    monkeypatch.setattr(
        "app.services.discount_rule.get_discount_rule_by_name",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        "app.services.discount_rule.create_discount_rule",
        create_record,
    )
    monkeypatch.setattr(
        "app.services.discount_rule.create_operation_audit_log",
        audit_record,
    )
    monkeypatch.setattr(
        "app.services.discount_rule.get_discount_rule_by_id",
        AsyncMock(return_value=rule),
    )

    db = AsyncMock(spec=AsyncSession)
    result = await create_discount_rule_service(
        request=CreateDiscountRuleRequest(
            department_id=1,
            name="晚间生鲜八折",
            discount_type=DiscountType.PERCENTAGE,
            discount_value=Decimal("0.8000"),
            schedule_type=DiscountScheduleType.DAILY,
            daily_start_time=time(18, 0),
            daily_end_time=time(21, 0),
        ),
        current_employee_id=employee.id,
        db=db,
    )

    assert result.name == "晚间生鲜八折"
    assert result.computed_status in (
        DiscountComputedStatus.ACTIVE,
        DiscountComputedStatus.SCHEDULED,
    )
    create_record.assert_awaited_once()
    audit_record.assert_awaited_once()
    db.commit.assert_awaited_once()


async def test_regular_employee_with_department_can_create_discount_rule(monkeypatch) -> None:
    """已分配部门的正式员工可以创建规则，商品范围在后续接口中限制为本部门。"""

    employee = build_regular_employee()
    now = datetime.now()
    rule = build_once_rule(now)
    rule.name = "本部门晚间折扣"
    rule.created_by = employee.id
    rule.creator = employee

    monkeypatch.setattr(
        "app.services.discount_rule.get_employee_by_id",
        AsyncMock(return_value=employee),
    )
    monkeypatch.setattr(
        "app.services.discount_rule.get_department_by_id",
        AsyncMock(return_value=build_department()),
    )
    monkeypatch.setattr(
        "app.services.discount_rule.get_discount_rule_by_name",
        AsyncMock(return_value=None),
    )
    create_record = AsyncMock(return_value=rule)
    monkeypatch.setattr(
        "app.services.discount_rule.create_discount_rule",
        create_record,
    )
    monkeypatch.setattr(
        "app.services.discount_rule.create_operation_audit_log",
        AsyncMock(),
    )
    monkeypatch.setattr(
        "app.services.discount_rule.get_discount_rule_by_id",
        AsyncMock(return_value=rule),
    )

    db = AsyncMock(spec=AsyncSession)
    result = await create_discount_rule_service(
        request=CreateDiscountRuleRequest(
            department_id=1,
            name="本部门晚间折扣",
            discount_type=DiscountType.PERCENTAGE,
            discount_value=Decimal("0.8000"),
            schedule_type=DiscountScheduleType.ONCE,
            starts_at=now + timedelta(hours=1),
            ends_at=now + timedelta(hours=2),
        ),
        current_employee_id=employee.id,
        db=db,
    )

    assert result.created_by == employee.id
    create_record.assert_awaited_once()
    db.commit.assert_awaited_once()


async def test_regular_employee_without_department_cannot_create_discount_rule(
    monkeypatch,
) -> None:
    """未分配部门的正式员工无法确定管理范围，因此不能创建折扣规则。"""

    employee = build_regular_employee(department_id=None)
    monkeypatch.setattr(
        "app.services.discount_rule.get_employee_by_id",
        AsyncMock(return_value=employee),
    )

    with pytest.raises(HTTPException) as exception_info:
        await create_discount_rule_service(
            request=CreateDiscountRuleRequest(
                department_id=1,
                name="无所属部门折扣",
                discount_type=DiscountType.PERCENTAGE,
                discount_value=Decimal("0.8000"),
                schedule_type=DiscountScheduleType.DAILY,
                daily_start_time=time(18, 0),
                daily_end_time=time(21, 0),
            ),
            current_employee_id=employee.id,
            db=AsyncMock(spec=AsyncSession),
        )

    assert exception_info.value.status_code == 403
    assert exception_info.value.detail == "正式员工未分配所属部门，不能创建折扣规则"


async def test_create_discount_rule_rejects_invalid_percentage(monkeypatch) -> None:
    """比例折扣为1或更大时应在写入数据库前返回400。"""

    employee = build_employee()
    monkeypatch.setattr(
        "app.services.discount_rule.get_employee_by_id",
        AsyncMock(return_value=employee),
    )
    monkeypatch.setattr(
        "app.services.discount_rule.get_department_by_id",
        AsyncMock(return_value=build_department()),
    )
    monkeypatch.setattr(
        "app.services.discount_rule.get_discount_rule_by_name",
        AsyncMock(return_value=None),
    )

    with pytest.raises(HTTPException) as exception_info:
        await create_discount_rule_service(
            request=CreateDiscountRuleRequest(
                department_id=1,
                name="无效比例折扣",
                discount_type=DiscountType.PERCENTAGE,
                discount_value=Decimal("1.0000"),
                schedule_type=DiscountScheduleType.DAILY,
                daily_start_time=time(18, 0),
                daily_end_time=time(21, 0),
            ),
            current_employee_id=employee.id,
            db=AsyncMock(spec=AsyncSession),
        )

    assert exception_info.value.status_code == 400


async def test_manager_can_add_products_from_rule_department(monkeypatch) -> None:
    """店长可以把规则所属部门的多个商品加入折扣。"""

    employee = build_employee()
    rule = build_once_rule(datetime.now())
    products = [
        build_product(product_id=1, department_id=1),
        build_product(product_id=2, department_id=1),
    ]
    monkeypatch.setattr(
        "app.services.discount_rule.get_employee_by_id",
        AsyncMock(return_value=employee),
    )
    monkeypatch.setattr(
        "app.services.discount_rule.get_discount_rule_by_id",
        AsyncMock(return_value=rule),
    )
    monkeypatch.setattr(
        "app.services.discount_rule.get_discount_products_by_ids",
        AsyncMock(return_value=products),
    )
    monkeypatch.setattr(
        "app.services.discount_rule.get_existing_discount_product_ids",
        AsyncMock(return_value=set()),
    )
    create_scopes = AsyncMock()
    monkeypatch.setattr(
        "app.services.discount_rule.create_discount_rule_product_scopes",
        create_scopes,
    )
    monkeypatch.setattr(
        "app.services.discount_rule.create_operation_audit_log",
        AsyncMock(),
    )

    db = AsyncMock(spec=AsyncSession)
    result = await add_discount_rule_products_service(
        discount_rule_id=rule.id,
        request=AddDiscountRuleProductsRequest(product_ids=[2, 1, 1]),
        current_employee_id=employee.id,
        db=db,
    )

    assert result.discount_rule_id == rule.id
    assert result.product_ids == [1, 2]
    create_scopes.assert_awaited_once_with(
        discount_rule_id=rule.id,
        product_ids=[1, 2],
        db=db,
    )
    db.commit.assert_awaited_once()


async def test_cannot_add_product_from_other_department(monkeypatch) -> None:
    """任何员工把其他部门商品加入规则时，都应在写入关联前返回400。"""

    employee = build_regular_employee(department_id=1)
    rule = build_once_rule(datetime.now())
    monkeypatch.setattr(
        "app.services.discount_rule.get_employee_by_id",
        AsyncMock(return_value=employee),
    )
    monkeypatch.setattr(
        "app.services.discount_rule.get_discount_rule_by_id",
        AsyncMock(return_value=rule),
    )
    monkeypatch.setattr(
        "app.services.discount_rule.get_discount_products_by_ids",
        AsyncMock(return_value=[build_product(product_id=8, department_id=2)]),
    )

    with pytest.raises(HTTPException) as exception_info:
        await add_discount_rule_products_service(
            discount_rule_id=rule.id,
            request=AddDiscountRuleProductsRequest(product_ids=[8]),
            current_employee_id=employee.id,
            db=AsyncMock(spec=AsyncSession),
        )

    assert exception_info.value.status_code == 400
    assert exception_info.value.detail == "折扣商品必须属于规则指定的部门：8"


async def test_get_discount_rule_products_service_builds_page_and_price(monkeypatch) -> None:
    """折扣商品列表应返回分页资料、商品信息以及计算后的折后价。"""

    employee = build_employee()
    now = datetime.now()
    rule = build_once_rule(now)
    department = Department(id=1, name="生鲜部", is_active=True)
    category = Category(id=1, department_id=1, name="肉类", is_active=True)
    product = Product(
        id=1,
        product_no="P00001",
        name="猪五花肉",
        supplier_product_id=1,
        department_id=1,
        category_id=1,
        purchase_price=Decimal("5.00"),
        sale_price=Decimal("10.00"),
        stock_quantity=20,
        status=ProductStatus.ON_SALE,
    )
    product.department = department
    product.category = category
    scope = DiscountRuleScope(
        id=10,
        discount_rule_id=rule.id,
        scope_type=DiscountScopeType.PRODUCT,
        product_id=product.id,
        created_at=now,
    )
    scope.product = product

    monkeypatch.setattr(
        "app.services.discount_rule.get_employee_by_id",
        AsyncMock(return_value=employee),
    )
    monkeypatch.setattr(
        "app.services.discount_rule.get_discount_rule_by_id",
        AsyncMock(return_value=rule),
    )
    list_query = AsyncMock(return_value=([scope], 1))
    monkeypatch.setattr(
        "app.services.discount_rule.get_discount_rule_products_list",
        list_query,
    )

    db = AsyncMock(spec=AsyncSession)
    result = await get_discount_rule_products_service(
        discount_rule_id=rule.id,
        request=GetDiscountRuleProductsRequest(
            page=1,
            page_size=10,
            keyword="猪肉",
            category_id=1,
        ),
        current_employee_id=employee.id,
        db=db,
    )

    assert result.total == 1
    assert result.total_pages == 1
    assert result.items[0].scope_id == 10
    assert result.items[0].product_name == "猪五花肉"
    assert result.items[0].original_price == Decimal("10.00")
    assert result.items[0].discounted_price == Decimal("8.00")
    list_query.assert_awaited_once_with(
        discount_rule_id=rule.id,
        offset=0,
        page_size=10,
        keyword="猪肉",
        category_id=1,
        db=db,
    )


async def test_manager_can_delete_one_discount_product(monkeypatch) -> None:
    """店长删除单件折扣商品时，只删除关联并写入审计记录。"""

    employee = build_employee()
    rule = build_once_rule(datetime.now())
    product = build_product(product_id=3, department_id=2)
    product.name = "测试商品"
    scope = DiscountRuleScope(
        id=20,
        discount_rule_id=rule.id,
        scope_type=DiscountScopeType.PRODUCT,
        product_id=product.id,
    )
    scope.product = product

    monkeypatch.setattr(
        "app.services.discount_rule.get_employee_by_id",
        AsyncMock(return_value=employee),
    )
    monkeypatch.setattr(
        "app.services.discount_rule.get_discount_rule_by_id",
        AsyncMock(return_value=rule),
    )
    monkeypatch.setattr(
        "app.services.discount_rule.get_discount_rule_product_scope",
        AsyncMock(return_value=scope),
    )
    delete_scopes = AsyncMock()
    monkeypatch.setattr(
        "app.services.discount_rule.delete_discount_rule_product_scopes",
        delete_scopes,
    )
    audit_log = AsyncMock()
    monkeypatch.setattr(
        "app.services.discount_rule.create_operation_audit_log",
        audit_log,
    )

    db = AsyncMock(spec=AsyncSession)
    result = await delete_discount_rule_product_service(
        discount_rule_id=rule.id,
        product_id=product.id,
        current_employee_id=employee.id,
        db=db,
    )

    assert result.deleted_count == 1
    assert result.deleted_product_ids == [3]
    delete_scopes.assert_awaited_once_with(scopes=[scope], db=db)
    audit_log.assert_awaited_once()
    db.commit.assert_awaited_once()


async def test_regular_employee_cannot_delete_other_department_discount_product(
    monkeypatch,
) -> None:
    """正式员工删除其他部门的折扣商品时返回403。"""

    employee = build_regular_employee(department_id=1)
    rule = build_once_rule(datetime.now())
    product = build_product(product_id=8, department_id=2)
    scope = DiscountRuleScope(
        id=21,
        discount_rule_id=rule.id,
        scope_type=DiscountScopeType.PRODUCT,
        product_id=product.id,
    )
    scope.product = product
    monkeypatch.setattr(
        "app.services.discount_rule.get_employee_by_id",
        AsyncMock(return_value=employee),
    )
    monkeypatch.setattr(
        "app.services.discount_rule.get_discount_rule_by_id",
        AsyncMock(return_value=rule),
    )
    monkeypatch.setattr(
        "app.services.discount_rule.get_discount_rule_product_scope",
        AsyncMock(return_value=scope),
    )

    with pytest.raises(HTTPException) as exception_info:
        await delete_discount_rule_product_service(
            discount_rule_id=rule.id,
            product_id=product.id,
            current_employee_id=employee.id,
            db=AsyncMock(spec=AsyncSession),
        )

    assert exception_info.value.status_code == 403


async def test_regular_employee_deletes_all_products_in_own_department(monkeypatch) -> None:
    """正式员工批量删除时，CRUD只查询其所属部门的商品关联。"""

    employee = build_regular_employee(department_id=1)
    rule = build_once_rule(datetime.now())
    product = build_product(product_id=5, department_id=1)
    scope = DiscountRuleScope(
        id=22,
        discount_rule_id=rule.id,
        scope_type=DiscountScopeType.PRODUCT,
        product_id=product.id,
    )
    scope.product = product
    monkeypatch.setattr(
        "app.services.discount_rule.get_employee_by_id",
        AsyncMock(return_value=employee),
    )
    monkeypatch.setattr(
        "app.services.discount_rule.get_discount_rule_by_id",
        AsyncMock(return_value=rule),
    )
    get_scopes = AsyncMock(return_value=[scope])
    monkeypatch.setattr(
        "app.services.discount_rule.get_discount_rule_product_scopes_for_delete",
        get_scopes,
    )
    monkeypatch.setattr(
        "app.services.discount_rule.delete_discount_rule_product_scopes",
        AsyncMock(),
    )
    monkeypatch.setattr(
        "app.services.discount_rule.create_operation_audit_log",
        AsyncMock(),
    )

    db = AsyncMock(spec=AsyncSession)
    result = await delete_all_discount_rule_products_service(
        discount_rule_id=rule.id,
        current_employee_id=employee.id,
        db=db,
    )

    assert result.deleted_count == 1
    assert result.deleted_product_ids == [5]
    get_scopes.assert_awaited_once_with(
        discount_rule_id=rule.id,
        department_id=1,
        db=db,
    )
    db.commit.assert_awaited_once()


async def test_manager_can_delete_one_discount_rule(monkeypatch) -> None:
    """店长删除单条规则时，应记录审计并调用规则删除函数。"""

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
    delete_rules = AsyncMock()
    monkeypatch.setattr(
        "app.services.discount_rule.delete_discount_rules",
        delete_rules,
    )
    audit_log = AsyncMock()
    monkeypatch.setattr(
        "app.services.discount_rule.create_operation_audit_log",
        audit_log,
    )

    db = AsyncMock(spec=AsyncSession)
    result = await delete_discount_rule_service(
        discount_rule_id=rule.id,
        current_employee_id=employee.id,
        db=db,
    )

    assert result.deleted_count == 1
    assert result.deleted_rule_ids == [rule.id]
    delete_rules.assert_awaited_once_with(rule_ids=[rule.id], db=db)
    audit_log.assert_awaited_once()
    db.commit.assert_awaited_once()


async def test_regular_employee_cannot_delete_other_department_rule(monkeypatch) -> None:
    """正式员工删除其他部门的折扣规则时返回403。"""

    employee = build_regular_employee(department_id=1)
    rule = build_once_rule(datetime.now())
    rule.department_id = 2
    rule.department = build_department(department_id=2)
    monkeypatch.setattr(
        "app.services.discount_rule.get_employee_by_id",
        AsyncMock(return_value=employee),
    )
    monkeypatch.setattr(
        "app.services.discount_rule.get_discount_rule_by_id",
        AsyncMock(return_value=rule),
    )

    with pytest.raises(HTTPException) as exception_info:
        await delete_discount_rule_service(
            discount_rule_id=rule.id,
            current_employee_id=employee.id,
            db=AsyncMock(spec=AsyncSession),
        )

    assert exception_info.value.status_code == 403


async def test_regular_employee_clears_rules_in_own_department(monkeypatch) -> None:
    """正式员工一键清空时，只查询和删除自己部门的折扣规则。"""

    employee = build_regular_employee(department_id=1)
    first_rule = build_once_rule(datetime.now())
    second_rule = build_once_rule(datetime.now())
    second_rule.id = 2
    second_rule.name = "第二条测试规则"
    rules = [first_rule, second_rule]
    monkeypatch.setattr(
        "app.services.discount_rule.get_employee_by_id",
        AsyncMock(return_value=employee),
    )
    get_rules = AsyncMock(return_value=rules)
    monkeypatch.setattr(
        "app.services.discount_rule.get_discount_rules_for_delete",
        get_rules,
    )
    delete_rules = AsyncMock()
    monkeypatch.setattr(
        "app.services.discount_rule.delete_discount_rules",
        delete_rules,
    )
    audit_log = AsyncMock()
    monkeypatch.setattr(
        "app.services.discount_rule.create_operation_audit_log",
        audit_log,
    )

    db = AsyncMock(spec=AsyncSession)
    result = await clear_discount_rules_service(
        current_employee_id=employee.id,
        db=db,
    )

    assert result.deleted_count == 2
    assert result.deleted_rule_ids == [1, 2]
    get_rules.assert_awaited_once_with(department_id=1, db=db)
    delete_rules.assert_awaited_once_with(rule_ids=[1, 2], db=db)
    assert audit_log.await_count == 2
    db.commit.assert_awaited_once()


async def test_regular_employee_can_close_own_department_rule(monkeypatch) -> None:
    """正式员工可以关闭自己部门的规则，并记录状态变化和原因。"""

    employee = build_regular_employee(department_id=1)
    rule = build_once_rule(datetime.now())
    updated_rule = build_once_rule(datetime.now(), is_active=False)
    monkeypatch.setattr(
        "app.services.discount_rule.get_employee_by_id",
        AsyncMock(return_value=employee),
    )
    monkeypatch.setattr(
        "app.services.discount_rule.get_discount_rule_by_id",
        AsyncMock(side_effect=[rule, updated_rule]),
    )
    update_status = AsyncMock()
    monkeypatch.setattr(
        "app.services.discount_rule.update_discount_rule_status",
        update_status,
    )
    audit_log = AsyncMock()
    monkeypatch.setattr(
        "app.services.discount_rule.create_operation_audit_log",
        audit_log,
    )

    db = AsyncMock(spec=AsyncSession)
    result = await update_discount_rule_status_service(
        discount_rule_id=rule.id,
        request=UpdateDiscountRuleStatusRequest(
            is_active=False,
            reason="本周暂停活动",
        ),
        current_employee_id=employee.id,
        db=db,
    )

    assert result.is_active is False
    assert result.computed_status == DiscountComputedStatus.DISABLED
    update_status.assert_awaited_once_with(
        discount_rule_id=rule.id,
        is_active=False,
        db=db,
    )
    audit_log.assert_awaited_once()
    assert audit_log.await_args.kwargs["reason"] == "本周暂停活动"
    db.commit.assert_awaited_once()


async def test_same_discount_status_does_not_update_or_audit(monkeypatch) -> None:
    """目标状态与当前状态相同时，直接返回且不更新数据库或写审计。"""

    employee = build_employee()
    rule = build_once_rule(datetime.now(), is_active=True)
    monkeypatch.setattr(
        "app.services.discount_rule.get_employee_by_id",
        AsyncMock(return_value=employee),
    )
    monkeypatch.setattr(
        "app.services.discount_rule.get_discount_rule_by_id",
        AsyncMock(return_value=rule),
    )
    update_status = AsyncMock()
    monkeypatch.setattr(
        "app.services.discount_rule.update_discount_rule_status",
        update_status,
    )
    audit_log = AsyncMock()
    monkeypatch.setattr(
        "app.services.discount_rule.create_operation_audit_log",
        audit_log,
    )

    db = AsyncMock(spec=AsyncSession)
    result = await update_discount_rule_status_service(
        discount_rule_id=rule.id,
        request=UpdateDiscountRuleStatusRequest(is_active=True),
        current_employee_id=employee.id,
        db=db,
    )

    assert result.is_active is True
    update_status.assert_not_awaited()
    audit_log.assert_not_awaited()
    db.commit.assert_not_awaited()


async def test_manager_can_update_discount_rule_and_change_schedule(monkeypatch) -> None:
    """店长可以把单次规则改成每日规则，并自动清理单次活动时间。"""

    employee = build_employee()
    original_rule = build_once_rule(datetime.now())
    updated_rule = build_once_rule(datetime.now())
    updated_rule.name = "每日晚间折扣"
    updated_rule.schedule_type = DiscountScheduleType.DAILY
    updated_rule.starts_at = None
    updated_rule.ends_at = None
    updated_rule.daily_start_time = time(18, 0)
    updated_rule.daily_end_time = time(21, 0)
    updated_rule.weekdays = None

    monkeypatch.setattr(
        "app.services.discount_rule.get_employee_by_id",
        AsyncMock(return_value=employee),
    )
    monkeypatch.setattr(
        "app.services.discount_rule.get_discount_rule_by_id",
        AsyncMock(side_effect=[original_rule, updated_rule]),
    )
    monkeypatch.setattr(
        "app.services.discount_rule.get_discount_rule_by_name",
        AsyncMock(return_value=None),
    )
    update_rule = AsyncMock()
    monkeypatch.setattr(
        "app.services.discount_rule.update_discount_rule",
        update_rule,
    )
    audit_log = AsyncMock()
    monkeypatch.setattr(
        "app.services.discount_rule.create_operation_audit_log",
        audit_log,
    )

    db = AsyncMock(spec=AsyncSession)
    request = UpdateDiscountRuleRequest(
        name="每日晚间折扣",
        schedule_type=DiscountScheduleType.DAILY,
        daily_start_time=time(18, 0),
        daily_end_time=time(21, 0),
        reason="改为每天执行",
    )
    result = await update_discount_rule_service(
        discount_rule_id=original_rule.id,
        request=request,
        current_employee_id=employee.id,
        db=db,
    )

    assert result.name == "每日晚间折扣"
    assert result.schedule_type == DiscountScheduleType.DAILY
    update_rule.assert_awaited_once()
    saved_data = update_rule.await_args.kwargs["update_data"]
    assert saved_data["starts_at"] is None
    assert saved_data["ends_at"] is None
    assert saved_data["daily_start_time"] == time(18, 0)
    assert saved_data["daily_end_time"] == time(21, 0)
    audit_log.assert_awaited_once()
    assert audit_log.await_args.kwargs["reason"] == "改为每天执行"
    db.commit.assert_awaited_once()


async def test_regular_employee_cannot_update_other_department_rule(monkeypatch) -> None:
    """正式员工不能修改其他部门的折扣规则。"""

    employee = build_regular_employee(department_id=1)
    rule = build_once_rule(datetime.now())
    rule.department_id = 2
    rule.department = build_department(department_id=2)
    monkeypatch.setattr(
        "app.services.discount_rule.get_employee_by_id",
        AsyncMock(return_value=employee),
    )
    monkeypatch.setattr(
        "app.services.discount_rule.get_discount_rule_by_id",
        AsyncMock(return_value=rule),
    )

    with pytest.raises(HTTPException) as exception_info:
        await update_discount_rule_service(
            discount_rule_id=rule.id,
            request=UpdateDiscountRuleRequest(name="不能修改的规则"),
            current_employee_id=employee.id,
            db=AsyncMock(spec=AsyncSession),
        )

    assert exception_info.value.status_code == 403


async def test_update_discount_rule_without_fields_is_rejected(monkeypatch) -> None:
    """未提交任何资料字段时返回400，避免执行无意义的数据库更新。"""

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

    with pytest.raises(HTTPException) as exception_info:
        await update_discount_rule_service(
            discount_rule_id=rule.id,
            request=UpdateDiscountRuleRequest(),
            current_employee_id=employee.id,
            db=AsyncMock(spec=AsyncSession),
        )

    assert exception_info.value.status_code == 400


async def test_product_discount_price_uses_lowest_active_rule(monkeypatch) -> None:
    """同一商品存在多条有效规则时，应选择折后价最低的一条且不叠加。"""

    now = datetime.now()
    product = build_product(product_id=1, department_id=1)
    product.category_id = 1
    product.name = "测试牛肉"
    product.sale_price = Decimal("100.00")
    product.status = ProductStatus.ON_SALE

    ninety_percent_rule = build_once_rule(now)
    ninety_percent_rule.id = 1
    ninety_percent_rule.name = "九折"
    ninety_percent_rule.discount_value = Decimal("0.9000")
    ninety_percent_scope = DiscountRuleScope(
        discount_rule_id=ninety_percent_rule.id,
        scope_type=DiscountScopeType.PRODUCT,
        product_id=product.id,
    )
    ninety_percent_rule.scopes = [ninety_percent_scope]

    eighty_percent_rule = build_once_rule(now)
    eighty_percent_rule.id = 2
    eighty_percent_rule.name = "八折"
    eighty_percent_rule.discount_value = Decimal("0.8000")
    eighty_percent_scope = DiscountRuleScope(
        discount_rule_id=eighty_percent_rule.id,
        scope_type=DiscountScopeType.PRODUCT,
        product_id=product.id,
    )
    eighty_percent_rule.scopes = [eighty_percent_scope]

    monkeypatch.setattr(
        "app.services.discount_rule.get_discount_products_by_ids",
        AsyncMock(return_value=[product]),
    )
    monkeypatch.setattr(
        "app.services.discount_rule.get_active_discount_rules_for_products",
        AsyncMock(return_value=[ninety_percent_rule, eighty_percent_rule]),
    )

    prices = await get_product_discount_prices(
        product_ids=[product.id],
        now=now,
        db=AsyncMock(spec=AsyncSession),
    )

    assert prices[product.id].original_unit_price == Decimal("100.00")
    assert prices[product.id].final_unit_price == Decimal("80.00")
    assert prices[product.id].discount_rule is eighty_percent_rule
