"""Exercise real ORM store scoping and headquarters services with two isolated stores."""

from datetime import timedelta
from decimal import Decimal

import pytest
from fastapi import HTTPException
from sqlalchemy import update
from starlette.requests import Request
from store_fixtures import set_request_store

from app.core.business_time import business_now
from app.core.exceptions import ConcurrentUpdateError
from app.crud.categories import get_categories_list
from app.crud.departments import get_departments_list
from app.crud.employees import get_list_employees
from app.crud.products import get_product_by_id, update_product
from app.models.employee import Employee
from app.models.enums import EmployeeRole, ProductStatus, PurchaseStatus, SaleSource
from app.models.product import Product
from app.models.purchase import Purchase
from app.models.sale import Sale
from app.models.store import StoreDepartment
from app.schemas.products_requests import ProductStatusUpdateRequest, UpdateProductRequest
from app.schemas.stores import EmployeeTransferRequest, StoreWriteRequest
from app.services.employees import create_employee_service, get_employee_detail_service
from app.services.products import (
    get_product_detail_service,
    update_product_service,
    update_product_status_service,
)
from app.services.reports import overview_service
from app.services.stores import check_department_can_disable
from app.services.stores import create_store_service as create_store
from app.services.stores import transfer_employee_service as transfer_employee


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
        result = await get_product_detail_service(
            2, db, employee_id, http_request=request(store="2")
        )
        assert result.id == 2
        with pytest.raises(HTTPException) as error:
            await update_product_status_service(
                2,
                ProductStatusUpdateRequest(status=ProductStatus.STOPPED),
                employee_id,
                db,
                http_request=request("/api/v1/products/2/status", "PUT", "2"),
            )
        assert error.value.status_code == 403
        with pytest.raises(HTTPException) as error:
            await get_employee_detail_service(
                5, employee_id, db, http_request=request("/api/v1/employees/5", store="2")
            )
        assert error.value.status_code == 403


async def test_service_and_crud_explicitly_limit_cross_store_updates(store_database):
    async with store_database() as db:
        with pytest.raises(HTTPException):
            await update_product_service(
                2,
                UpdateProductRequest(name="unauthorized"),
                1,
                db,
                http_request=request("/api/v1/products/2", "PUT", "2"),
            )
        assert (await db.get(Product, 2)).name == "Product 2"
        # CRUD 也有店铺条件，不能在1号店的范围里更新2号店的数据。
        await set_request_store(request(store="1"), await db.get(Employee, 1), db)
        with pytest.raises(ConcurrentUpdateError):
            await update_product(2, {"name": "unauthorized"}, 1, db)
        await db.rollback()
        assert (await db.get(Product, 2)).name == "Product 2"


async def test_explicit_queries_restrict_products_departments_and_staff(store_database):
    async with store_database() as db:
        for store in ("1", "2", "1"):
            result = await get_product_detail_service(
                int(store), db, 2, http_request=request(store=store)
            )
            assert result.id == int(store)
            assert await get_product_by_id(3 - int(store), db) is None
        assert [row.id for row in await get_departments_list(db)] == [1]
        assert [row.id for row in await get_categories_list(None, db)] == [1]
        await set_request_store(request("/api/v1/employees/list"), await db.get(Employee, 1), db)
        employees, total = await get_list_employees(1, 20, None, None, None, db)
        assert {row.id for row in employees} == {1, 2, 3}
        assert total == 3


async def test_headquarters_cannot_run_daily_store_operations(store_database):
    async with store_database() as db:
        with pytest.raises(HTTPException) as error:
            await update_product_status_service(
                1,
                ProductStatusUpdateRequest(status=ProductStatus.STOPPED),
                4,
                db,
                http_request=request("/api/v1/products/1/status", "PUT"),
            )
        assert error.value.status_code == 403


async def test_only_headquarters_can_request_all_store_reports(store_database):
    now = business_now()
    async with store_database() as db:
        for employee_id in (1, 2, 3):
            with pytest.raises(HTTPException) as error:
                await overview_service(
                    db=db,
                    employee_id=employee_id,
                    start_time=now - timedelta(hours=1),
                    end_time=now,
                    department_id=None,
                    http_request=request("/api/v1/reports/overview", store="all"),
                )
            assert error.value.status_code == 403
        await overview_service(
            db=db,
            employee_id=4,
            start_time=now - timedelta(hours=1),
            end_time=now,
            department_id=None,
            http_request=request("/api/v1/reports/overview", store="all"),
        )
        assert db.info["read_store_id"] is None


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
            await set_request_store(request("/api/v1/reports/overview", store=scope), actor, db)
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
        await set_request_store(request("/api/v1/stores", "POST"), actor, db)
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
        await set_request_store(request("/api/v1/stores/1/departments/1", "PUT", "2"), actor, db)
        if blocker == "none":
            await check_department_can_disable(1, 1, db)
        else:
            with pytest.raises(HTTPException) as error:
                await check_department_can_disable(1, 1, db)
            assert error.value.status_code == 409
        assert db.info["read_store_id"] == 2


async def test_store_manager_cannot_use_headquarters_management(store_database):
    async with store_database() as db:
        await set_request_store(request("/api/v1/stores", "POST"), await db.get(Employee, 1), db)
        with pytest.raises(HTTPException) as error:
            await create_store(StoreWriteRequest(name="Forbidden store"), 1, db)
        assert error.value.status_code == 403


async def test_store_manager_cannot_create_manager_or_headquarters(store_database):
    async with store_database() as db:
        for role in (EmployeeRole.STORE_MANAGER, EmployeeRole.HEADQUARTERS):
            with pytest.raises(HTTPException) as error:
                await create_employee_service(
                    "Forbidden", role, 1, 1, db, http_request=request("/api/v1/employees", "POST")
                )
            assert error.value.status_code == 403
        assert (await db.get(Employee, 2)).role == EmployeeRole.REGULAR_EMPLOYEE


async def test_http_store_filters_and_cache_recheck_account(store_database):
    """走真实 JWT、路由、服务、CRUD，确认跨店缓存不会混用，也不会绕过停用检查。"""
    from fastapi_cache import FastAPICache
    from fastapi_cache.backends.inmemory import InMemoryBackend
    from httpx2 import ASGITransport, AsyncClient

    from app.core.token import create_access_token
    from app.dependencies.db import get_db
    from app.main import create_app

    async with store_database() as db:
        db.add(StoreDepartment(store_id=2, department_id=2, is_active=True))
        await db.commit()

    application = create_app()

    async def database():
        async with store_database() as db:
            yield db

    application.dependency_overrides[get_db] = database
    FastAPICache.reset()
    FastAPICache.init(InMemoryBackend(), prefix="explicit-store-test")
    token = create_access_token({"sub": "1"})
    try:
        async with AsyncClient(
            transport=ASGITransport(app=application), base_url="http://test"
        ) as client:
            headers = {"Authorization": "Bearer " + token, "X-Store-ID": "1"}
            first = await client.get("/api/v1/categories/list", headers=headers)
            assert first.status_code == 200
            assert [item["id"] for item in first.json()["data"]] == [1]
            headers["X-Store-ID"] = "2"
            second = await client.get("/api/v1/categories/list", headers=headers)
            assert second.status_code == 200
            assert {item["id"] for item in second.json()["data"]} == {1, 2}
            products = await client.get("/api/v1/products/list", headers=headers)
            assert [item["id"] for item in products.json()["data"]["items"]] == [2]
            blocked = await client.put(
                "/api/v1/products/2", headers=headers, json={"name": "Blocked"}
            )
            assert blocked.status_code == 403
            async with store_database() as db:
                actor = await db.get(Employee, 1)
                actor.is_active = False
                await db.commit()
            headers["X-Store-ID"] = "1"
            disabled = await client.get("/api/v1/categories/list", headers=headers)
            assert disabled.status_code == 401
    finally:
        FastAPICache.reset()


async def test_http_new_supplier_belongs_to_actual_store(store_database):
    """没有 before_flush 后，CRUD 仍必须明确填写新增记录的所属店。"""
    from httpx2 import ASGITransport, AsyncClient

    from app.core.token import create_access_token
    from app.dependencies.db import get_db
    from app.main import create_app
    from app.models.supplier import Supplier

    async with store_database() as db:
        actor = await db.get(Employee, 5)
        actor.role = EmployeeRole.STORE_MANAGER
        await db.commit()
    application = create_app()

    async def database():
        async with store_database() as db:
            yield db

    application.dependency_overrides[get_db] = database
    headers = {
        "Authorization": "Bearer " + create_access_token({"sub": "5"}),
        "X-Store-ID": "2",
    }
    async with AsyncClient(
        transport=ASGITransport(app=application), base_url="http://test"
    ) as client:
        response = await client.post(
            "/api/v1/suppliers/", headers=headers, json={"name": "Second store supplier"}
        )
        assert response.status_code == 200
    async with store_database() as db:
        supplier = await db.get(Supplier, response.json()["data"]["id"])
        assert supplier.store_id == 2


@pytest.mark.parametrize("actor_id", [1, 4])
@pytest.mark.parametrize(
    "module_name,function_name,arguments",
    [
        ("suppliers", "create_supplier_service", {"request": None}),
        ("suppliers", "update_supplier_service", {"supplier_id": 2, "request": None}),
        ("supplier_products", "create_supplier_product_service", {"request": None}),
        (
            "supplier_products",
            "update_supplier_product_service",
            {"supplier_product_id": 2, "request": None},
        ),
        (
            "inventory_batches",
            "update_inventory_batch_quantity_service",
            {"batch_id": 1, "request": None},
        ),
        (
            "inventory_batches",
            "discard_expired_inventory_batch_service",
            {"batch_id": 1, "request": None},
        ),
        ("purchases", "receive_purchase_service", {"purchase_id": 1}),
        ("purchases", "auto_receive_purchases_service", {}),
        ("sales", "create_sale_service", {"request": None}),
        ("discount_rule", "create_discount_rule_service", {"request": None}),
        (
            "discount_rule",
            "add_discount_rule_products_service",
            {"discount_rule_id": 1, "request": None},
        ),
        (
            "discount_rule",
            "delete_all_discount_rule_products_service",
            {"discount_rule_id": 1},
        ),
        (
            "discount_rule",
            "update_discount_rule_status_service",
            {"discount_rule_id": 1, "request": None},
        ),
        (
            "employees",
            "create_employee_service",
            {"name": "Blocked", "role": EmployeeRole.REGULAR_EMPLOYEE, "department_id": 1},
        ),
        ("employees", "update_employee_status_service", {"employee_id": 5, "is_active": False}),
        ("employees", "reset_employee_password_service", {"employee_id": 5}),
        ("employees", "update_employee_detail_service", {"employee_id": 5, "request": None}),
    ],
)
async def test_each_write_service_rejects_headquarters_and_cross_store_changes(
    store_database, actor_id, module_name, function_name, arguments
):
    """拆开权限检查后，各业务入口都必须先拒绝越权，不能依赖原来的 ORM 事件。"""
    from importlib import import_module

    service = getattr(import_module("app.services." + module_name), function_name)
    async with store_database() as db:
        with pytest.raises(HTTPException) as error:
            await service(
                **arguments,
                current_employee_id=actor_id,
                db=db,
                http_request=request("/api/v1/example", "PUT", "2"),
            )
        assert error.value.status_code == 403


@pytest.mark.parametrize("actor_id", [1, 4])
async def test_plan_and_discard_write_services_reject_foreign_scope(store_database, actor_id):
    from app.services.inventory_discards import create_discard
    from app.services.purchase_plan_submission import save_minimum_stock, save_purchase_plan

    async with store_database() as db:
        for service in (save_minimum_stock, save_purchase_plan):
            with pytest.raises(HTTPException) as error:
                await service(
                    None,
                    actor_id,
                    db,
                    access_employee_id=actor_id,
                    http_request=request("/api/v1/purchases/planning", "PUT", "2"),
                )
            assert error.value.status_code == 403
        with pytest.raises(HTTPException) as error:
            await create_discard(
                None,
                actor_id,
                db,
                http_request=request("/api/v1/inventory-discards", "POST", "2"),
            )
        assert error.value.status_code == 403


async def test_inventory_audit_keeps_record_when_batch_no_longer_exists(store_database):
    """显式店铺条件不能把外连接变成内连接，丢掉已保存的审计记录。"""
    from app.crud.operation_audit_logs import get_inventory_movements
    from app.models.operation_audit_log import OperationAuditLog

    async with store_database() as db:
        db.add(
            OperationAuditLog(
                store_id=1,
                employee_id=1,
                module="inventory",
                action="discard_manual",
                target_type="inventory_batch",
                target_id=999,
                after_data={"batch_no": "OLD-BATCH"},
            )
        )
        await db.commit()
        await set_request_store(
            request("/api/v1/operation-audit-logs/inventory-movements", store="2"),
            await db.get(Employee, 1),
            db,
        )
        rows, total = await get_inventory_movements(0, 20, None, None, None, None, None, None, db)
        assert total == len(rows) == 1
        assert rows[0][0].store_id == 1
        assert rows[0][2] is None


async def test_global_category_change_checks_references_in_other_stores(store_database):
    from app.models.category import Category
    from app.schemas.stores import CompanyCategoryRequest
    from app.services.stores import company_category_service

    async with store_database() as db:
        # 分类1只剩2号店引用，总部当前下拉框选的是1号店。
        product = await db.get(Product, 1)
        product.category_id = 2
        product.department_id = 2
        await db.commit()
        with pytest.raises(HTTPException) as error:
            await company_category_service(
                CompanyCategoryRequest(name="Moved", department_id=2, is_active=True),
                1,
                4,
                db,
                http_request=request("/api/v1/stores/company-categories/1", "PUT", "1"),
            )
        assert error.value.status_code == 409
        assert (await db.get(Category, 1)).department_id == 1
