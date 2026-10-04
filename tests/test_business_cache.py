"""查询缓存命中、门店隔离及实时补货输入的数据库回归测试。"""

from datetime import date, datetime
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from fastapi_cache import FastAPICache
from fastapi_cache.backends.inmemory import InMemoryBackend
from sqlalchemy import event

from app.core import cache as cache_module
from app.crud.reports import get_reports
from app.models.employee import Employee
from app.models.enums import EmployeeRole
from app.models.purchase_plan import PurchasePlan
from app.models.sale import Sale
from app.models.sale_item import SaleItem
from app.models.supplier_product import SupplierProduct
from app.services.replenishment import calculate_replenishment, weekday_sales_forecast
from app.services.reports import overview_service


@pytest.fixture
async def query_cache():
    FastAPICache.reset()
    backend = InMemoryBackend()
    await backend.clear(namespace="business-tests")
    FastAPICache.init(backend, prefix="business-tests")
    try:
        yield backend
    finally:
        await backend.clear(namespace="business-tests")
        FastAPICache.reset()


def count_queries(db):
    statements = []

    @event.listens_for(db.get_bind(), "before_cursor_execute")
    def record(_connection, _cursor, statement, _parameters, _context, _many):
        statements.append(statement)

    return statements


async def test_forecast_shared_between_sessions_but_separates_store_and_date(
    store_database, query_cache
):
    today = date(2026, 10, 4)
    async with store_database() as db:
        # 上周日销量13/29，分别预测ceil(13/4)=4和ceil(29/4)=8。
        for store_id, quantity in ((1, 13), (2, 29)):
            sale = Sale(
                store_id=store_id,
                sale_no=f"HISTORY-{store_id}",
                sold_at=datetime(2026, 9, 27, 12),
                original_total_amount=quantity * 10,
                total_amount=quantity * 10,
                total_cost=quantity * 5,
                gross_profit=quantity * 5,
                items=[
                    SaleItem(
                        store_id=store_id,
                        product_id=store_id,
                        product_no_snapshot=f"P{store_id}",
                        product_name_snapshot="Test",
                        department_id=1,
                        quantity=quantity,
                        original_unit_price=10,
                        unit_price=10,
                        unit_cost=5,
                        subtotal=quantity * 10,
                        cost_subtotal=quantity * 5,
                    )
                ],
            )
            db.add(sale)
        await db.commit()
        statements = count_queries(db)
        first = await weekday_sales_forecast(1, (1,), today, db)
        assert first == {"1": [0, 0, 0, 0, 0, 0, 4]}
        assert len(statements) == 1
    async with store_database() as db:
        db.info.update(store_context=True, read_store_id=1, actor_role=EmployeeRole.HEADQUARTERS)
        assert (
            await weekday_sales_forecast(db=db, today=today, product_ids=(1,), store_id=1) == first
        )
        assert len(statements) == 1  # 请求和后台任务可共享相同门店的预测。
        db.info.clear()
        assert await weekday_sales_forecast(2, (2,), today, db) == {"2": [0, 0, 0, 0, 0, 0, 8]}
        await weekday_sales_forecast(1, (1,), date(2026, 10, 5), db)
        assert len(statements) == 3


async def test_historical_reports_hit_preserve_decimal_and_isolate_scope(
    store_database, query_cache, monkeypatch
):
    monkeypatch.setattr(cache_module, "business_now", lambda: datetime(2026, 10, 4, 11))
    start, end = datetime(2026, 10, 2, 9), datetime(2026, 10, 3, 21)
    async with store_database() as db:
        statements = count_queries(db)
        first = await get_reports(db, start, end, None)
        assert len(statements) == 2
        second = await get_reports(db=db, start_time=start, end_time=end, department_id=None)
        assert second == first and isinstance(second, tuple)
        assert isinstance(second[0], Decimal)
        assert len(statements) == 2
        db.info["read_store_id"] = 2
        await get_reports(db, start, end, None)
        assert len(statements) == 4
        end = datetime(2026, 10, 4, 21)
        await get_reports(db, start, end, None)
        await get_reports(db, start, end, None)
        assert len(statements) == 8  # 包含今天的报表每次都查询数据库。


async def test_cached_report_still_checks_disabled_account(
    store_database, query_cache, monkeypatch
):
    monkeypatch.setattr(cache_module, "business_now", lambda: datetime(2026, 10, 4, 11))
    async with store_database() as db:
        await overview_service(db, 1, datetime(2026, 10, 2, 9), datetime(2026, 10, 3, 21), None)
        employee = await db.get(Employee, 1)
        employee.is_active = False
        await db.commit()
        with pytest.raises(HTTPException) as error:
            await overview_service(db, 1, datetime(2026, 10, 2, 9), datetime(2026, 10, 3, 21), None)
        assert error.value.status_code == 403


async def test_replenishment_reads_minimum_stock_live_with_cached_forecast(
    store_database, query_cache
):
    async with store_database() as db:
        catalog = await db.get(SupplierProduct, 1)
        now, day = datetime(2026, 10, 4, 21), date(2026, 10, 6)
        statements = count_queries(db)
        first = await calculate_replenishment(1, 1, [day], [catalog], db, now)
        catalog.minimum_stock = 10
        await db.commit()
        second = await calculate_replenishment(1, 1, [day], [catalog], db, now)
        assert first[1][day]["planned_quantity"] == 0
        assert second[1][day]["planned_quantity"] == 10
        db.add(
            PurchasePlan(
                store_id=1,
                department_id=1,
                arrival_date=day,
                quantities={"1": 25},
                automatic_quantities={},
                updated_by=1,
            )
        )
        await db.commit()
        third = await calculate_replenishment(1, 1, [day], [catalog], db, now)
        assert third[1][day]["planned_quantity"] == 25
        assert third[1][day]["is_manual"]
        assert sum("sum(sale_item.quantity)" in statement.lower() for statement in statements) == 1


async def test_cache_outage_falls_back_to_database(store_database, query_cache, monkeypatch):
    monkeypatch.setattr(query_cache, "get", AsyncMock(side_effect=ConnectionError("offline")))
    monkeypatch.setattr(query_cache, "set", AsyncMock(side_effect=ConnectionError("offline")))
    async with store_database() as db:
        statements = count_queries(db)
        first = await weekday_sales_forecast(1, (1,), date(2026, 10, 4), db)
        second = await weekday_sales_forecast(1, (1,), date(2026, 10, 4), db)
        assert first == second == {"1": [0] * 7}
        assert len(statements) == 2


async def test_expired_cache_requeries_database(store_database, query_cache, monkeypatch):
    clock = [100]
    monkeypatch.setattr(InMemoryBackend, "_now", property(lambda self: clock[0]))
    async with store_database() as db:
        statements = count_queries(db)
        await weekday_sales_forecast(1, (1,), date(2026, 10, 4), db)
        clock[0] += cache_module.FORECAST_CACHE_SECONDS + 1
        await weekday_sales_forecast(1, (1,), date(2026, 10, 4), db)
        assert len(statements) == 2
