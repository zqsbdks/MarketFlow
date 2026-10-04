"""Real isolated transactions: date boundaries, exact costs and store isolation."""

from datetime import date, datetime
from decimal import Decimal

import pytest
from fastapi import HTTPException
from test_store_policy import request as http_request

from app.core.store_policy import configure_store_context
from app.models.inventory_discard import InventoryDiscard
from app.schemas.discard_analysis import DiscardAnalysisRequest
from app.services.discard_analysis import get_discard_analysis


@pytest.fixture
async def analysis_database(store_database):
    async with store_database() as db:
        for index, (store, hour, day, reason, qty, cost) in enumerate(
            [
                (1, 0, 4, "expired", 3, "10.01"),
                (1, 23, 4, "damaged", 2, "20.02"),
                (2, 12, 4, "expired", 5, "70.07"),
                (1, 0, 5, "expired", 99, "999.00"),
            ],
            1,
        ):
            db.add(
                InventoryDiscard(
                    store_id=store,
                    request_key=str(index),
                    product_id=store,
                    product_no=f"P{store}",
                    product_name="Demo",
                    department_id=1,
                    department_name="Department 1",
                    reason_code=reason,
                    quantity=qty,
                    total_cost=Decimal(cost),
                    created_at=datetime(2026, 10, day, hour),
                )
            )
        await db.commit()
    return store_database


def query(**changes):
    return DiscardAnalysisRequest(
        start_date=date(2026, 10, 4), end_date=date(2026, 10, 4), **changes
    )


@pytest.mark.asyncio
async def test_full_date_and_store_scope(analysis_database):
    from app.models.employee import Employee

    async with analysis_database() as db:
        actor = await db.get(Employee, 1)
        await configure_store_context(
            http_request(path="/api/v1/reports/discard-analysis", store="1"), actor, db
        )
        result = await get_discard_analysis(db, 1, query())
        assert (result.record_count, result.quantity, result.cost) == (2, 5, Decimal("30.03"))
        assert result.stores == []
        assert result.reasons[0].key == "damaged"
        assert result.reasons[0].cost_share == Decimal("66.67")
        empty = await get_discard_analysis(db, 1, query(department_id=2))
        assert empty.cost == 0 and empty.reasons == []


@pytest.mark.asyncio
async def test_company_totals_and_forbidden_all(analysis_database):
    from app.models.employee import Employee

    async with analysis_database() as db:
        actor = await db.get(Employee, 4)
        await configure_store_context(
            http_request(path="/api/v1/reports/discard-analysis", store="all"), actor, db
        )
        result = await get_discard_analysis(db, 4, query())
        assert (result.record_count, result.quantity, result.cost) == (3, 10, Decimal("100.10"))
        assert len(result.stores) == 2
        assert sum(item.cost for item in result.stores) == result.cost
        assert result.reasons[0].cost_share == Decimal("80.00")
    async with analysis_database() as db:
        actor = await db.get(Employee, 1)
        with pytest.raises(HTTPException) as exc:
            await configure_store_context(
                http_request(path="/api/v1/reports/discard-analysis", store="all"), actor, db
            )
        assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_invalid_range_and_disabled_account(analysis_database):
    from app.models.employee import Employee

    async with analysis_database() as db:
        with pytest.raises(HTTPException) as exc:
            await get_discard_analysis(
                db,
                1,
                DiscardAnalysisRequest(start_date=date(2026, 10, 5), end_date=date(2026, 10, 4)),
            )
        assert exc.value.status_code == 400
        actor = await db.get(Employee, 1)
        actor.is_active = False
        await db.flush()
        with pytest.raises(HTTPException) as exc:
            await get_discard_analysis(db, 1, query())
        assert exc.value.status_code == 403
