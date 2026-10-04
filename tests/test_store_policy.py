"""Exercise real ORM store scoping and headquarters services with two isolated stores."""

from datetime import timedelta
from decimal import Decimal

import pytest
from fastapi import HTTPException
from sqlalchemy import select, update
from starlette.requests import Request

from app.core.business_time import business_now
from app.core.store_policy import configure_store_context
from app.models.category import Category
from app.models.department import Department
from app.models.employee import Employee
from app.models.enums import EmployeeRole, PurchaseStatus, SaleSource
from app.models.product import Product
from app.models.purchase import Purchase
from app.models.sale import Sale
from app.models.store import StoreDepartment
from app.routers.stores import check_department_can_disable, create_store, transfer_employee
from app.schemas.stores import EmployeeTransferRequest, StoreWriteRequest
from app.services.reports import overview_service


def request(path="/api/v1/products/list", method="GET", store="1"):
    return Request(
        {
            "type": "http",
            "method": method,
            "path": path,
            "query_string": b"",
            "headers": [(b"x-store-id", store.encode())],
        }
    )


@pytest.mark.parametrize("employee_id", [1, 2, 3])
async def test_store_roles_can_read_other_store_but_not_write_or_read_staff(
    store_database, employee_id
):
    async with store_database() as db:
        actor = await db.get(Employee, employee_id)
        await configure_store_context(request(store="2"), actor, db)
        assert [row.id for row in (await db.scalars(select(Product))).all()] == [2]
        for path, method in [("/api/v1/products/2", "PUT"), ("/api/v1/employees/list", "GET")]:
            with pytest.raises(HTTPException) as error:
                await configure_store_context(request(path, method, "2"), actor, db)
            assert error.value.status_code == 403


async def test_orm_writes_cannot_bypass_cross_store_read_only(store_database):
    async with store_database() as db:
        actor = await db.get(Employee, 1)
        await configure_store_context(request(store="2"), actor, db)
        foreign_product = await db.get(Product, 2)
        foreign_product.name = "unauthorized change"
        with pytest.raises(HTTPException) as error:
            await db.flush()
        assert error.value.status_code == 403
        await db.rollback()
    async with store_database() as db:
        actor = await db.get(Employee, 1)
        await configure_store_context(request(store="2"), actor, db)
        with pytest.raises(HTTPException):
            await db.execute(update(Product).values(name="unauthorized bulk change"))
    async with store_database() as db:
        assert (await db.get(Product, 2)).name == "Product 2"


async def test_context_switch_restricts_products_departments_and_staff(store_database):
    async with store_database() as db:
        actor = await db.get(Employee, 2)
        for store in ("1", "2", "1"):
            await configure_store_context(request(store=store), actor, db)
            assert [row.id for row in (await db.scalars(select(Product))).all()] == [int(store)]
        assert [row.id for row in (await db.scalars(select(Department))).all()] == [1]
        assert [row.id for row in (await db.scalars(select(Category))).all()] == [1]
        await configure_store_context(request("/api/v1/employees/list"), actor, db)
        assert {row.id for row in (await db.scalars(select(Employee))).all()} == {1, 2, 3}


@pytest.mark.parametrize(
    "path", ["/api/v1/sales", "/api/v1/purchases/1/receive", "/api/v1/inventory-batches/1/quantity"]
)
async def test_headquarters_cannot_run_daily_store_operations(store_database, path):
    async with store_database() as db:
        actor = await db.get(Employee, 4)
        with pytest.raises(HTTPException) as error:
            await configure_store_context(request(path, "POST"), actor, db)
        assert error.value.status_code == 403


async def test_only_headquarters_can_request_all_store_reports(store_database):
    async with store_database() as db:
        for employee_id in (1, 2, 3):
            with pytest.raises(HTTPException):
                await configure_store_context(
                    request("/api/v1/reports/overview", store="all"),
                    await db.get(Employee, employee_id),
                    db,
                )
        await configure_store_context(
            request("/api/v1/reports/overview", store="all"), await db.get(Employee, 4), db
        )
        assert db.info["read_store_id"] is None
        assert {row.id for row in (await db.scalars(select(Product))).all()} == {1, 2}


async def test_headquarters_report_sums_both_stores(store_database):
    now = business_now().replace(hour=12, minute=0, second=0, microsecond=0)
    async with store_database() as db:
        for store, amount in [(1, Decimal("10")), (2, Decimal("25"))]:
            db.add(
                Sale(
                    store_id=store,
                    sale_no=f"TEST{store}",
                    sold_at=now,
                    original_total_amount=amount,
                    discount_amount=0,
                    total_amount=amount,
                    total_cost=0,
                    gross_profit=amount,
                    source=SaleSource.POS,
                )
            )
        await db.commit()
        actor = await db.get(Employee, 4)
        for scope, expected in [("1", Decimal("10")), ("2", Decimal("25")), ("all", Decimal("35"))]:
            await configure_store_context(
                request("/api/v1/reports/overview", store=scope), actor, db
            )
            result = await overview_service(
                db=db,
                employee_id=4,
                start_time=now - timedelta(hours=1),
                end_time=now + timedelta(hours=1),
                department_id=None,
            )
            assert result.revenue == expected


async def test_headquarters_create_store_and_transfer_staff(store_database):
    async with store_database() as db:
        actor = await db.get(Employee, 4)
        await configure_store_context(request("/api/v1/stores", "POST"), actor, db)
        result = await create_store(
            StoreWriteRequest(name="Third store", department_ids=[1]), 4, db
        )
        assert result.data["store_no"] == "DP0003"
        assert (await db.get(StoreDepartment, (result.data["id"], 1))).is_active
        await transfer_employee(2, EmployeeTransferRequest(store_id=2, department_id=1), 4, db)
        assert (await db.get(Employee, 2)).store_id == 2


@pytest.mark.parametrize("blocker", ["staff", "stock", "pending", "none"])
async def test_department_disabling_requires_empty_business_state(store_database, blocker):
    async with store_database() as db:
        await db.execute(
            update(Employee).where(Employee.department_id == 1).values(is_active=False)
        )
        if blocker == "staff":
            (await db.get(Employee, 2)).is_active = True
        if blocker == "stock":
            (await db.get(Product, 1)).stock_quantity = 2
        if blocker == "pending":
            db.add(
                Purchase(
                    store_id=1,
                    purchase_no="TESTP",
                    department_id=1,
                    created_by=1,
                    ordered_at=business_now(),
                    expected_arrival_at=business_now() + timedelta(days=2),
                    total_amount=0,
                    status=PurchaseStatus.PENDING,
                )
            )
        await db.commit()
        actor = await db.get(Employee, 4)
        await configure_store_context(
            request("/api/v1/stores/1/departments/1", "PUT", "2"), actor, db
        )
        if blocker == "none":
            await check_department_can_disable(1, 1, db)
        else:
            with pytest.raises(HTTPException) as error:
                await check_department_can_disable(1, 1, db)
            assert error.value.status_code == 409
        assert db.info["read_store_id"] == 2


async def test_store_manager_cannot_use_headquarters_management(store_database):
    async with store_database() as db:
        await configure_store_context(
            request("/api/v1/stores", "POST"), await db.get(Employee, 1), db
        )
        with pytest.raises(HTTPException) as error:
            await create_store(StoreWriteRequest(name="Forbidden store"), 1, db)
        assert error.value.status_code == 403


async def test_store_manager_cannot_promote_or_transfer_staff_in_regular_employee_path(
    store_database,
):
    async with store_database() as db:
        actor = await db.get(Employee, 1)
        await configure_store_context(request("/api/v1/employees/2", "PUT"), actor, db)
        employee = await db.get(Employee, 2)
        employee.role = EmployeeRole.STORE_MANAGER
        with pytest.raises(HTTPException):
            await db.flush()
