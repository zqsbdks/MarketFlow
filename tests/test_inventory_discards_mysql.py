"""独立临时 MySQL 库验证真正的行锁并发；绝不提交到演示业务库。"""

import asyncio
import os
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import create_async_engine
from store_fixtures import create_store_database
from test_inventory_discards import NOW, context, discard_database, payload

from app.models.inventory_discard import InventoryDiscard
from app.models.product import Product
from app.services.inventory_discards import create_discard, discard_expired_product

pytestmark = pytest.mark.integration


@pytest.fixture
async def mysql_discard_database(monkeypatch):
    if os.getenv("RUN_MYSQL_TESTS") != "1":
        pytest.skip("set RUN_MYSQL_TESTS=1; creates and drops an isolated temporary MySQL database")
    admin_url = os.getenv("MYSQL_DISCARD_TEST_ADMIN_URL")
    if not admin_url:
        pytest.skip("MYSQL_DISCARD_TEST_ADMIN_URL must allow creating isolated test databases")
    admin = create_async_engine(admin_url)
    database = "marketflow_discard_test_" + uuid4().hex
    engine = None
    created = False
    try:
        async with admin.begin() as connection:
            await connection.execute(text(f"CREATE DATABASE `{database}` CHARACTER SET utf8mb4"))
            created = True
        engine, factory = await create_store_database(admin.url.set(database=database))
        await discard_database.__wrapped__(factory, monkeypatch)
        yield factory
    finally:
        if engine is not None:
            await engine.dispose()
        if created:
            assert database.startswith("marketflow_discard_test_") and len(database) == 56
            async with admin.begin() as connection:
                await connection.execute(text(f"DROP DATABASE IF EXISTS `{database}`"))
        await admin.dispose()


async def test_mysql_concurrent_identical_requests_only_deduct_once(mysql_discard_database):
    req = payload(quantity=12)

    async def submit():
        async with mysql_discard_database() as db:
            await context(db)
            return await create_discard(req, 1, db)

    first, second = await asyncio.gather(submit(), submit())
    assert first.id == second.id
    assert first.model_dump() == second.model_dump()
    assert len(second.items) == 2
    async with mysql_discard_database() as db:
        assert (await db.get(Product, 1)).stock_quantity == 28
        assert await db.scalar(select(func.count(InventoryDiscard.id))) == 1


async def test_mysql_competing_requests_do_not_overdraw(mysql_discard_database):
    async def submit():
        async with mysql_discard_database() as db:
            await context(db)
            try:
                return await create_discard(payload(quantity=20), 1, db)
            except HTTPException as exc:
                await db.rollback()
                return exc.status_code

    results = await asyncio.gather(submit(), submit())
    assert sum(result == 400 for result in results) == 1
    async with mysql_discard_database() as db:
        assert (await db.get(Product, 1)).stock_quantity == 20
        assert await db.scalar(select(func.count(InventoryDiscard.id))) == 1


async def test_mysql_automatic_and_manual_disposal_preserve_stock_sum(mysql_discard_database):
    async def manual():
        async with mysql_discard_database() as db:
            await context(db)
            await create_discard(payload(quantity=12), 1, db)

    async def automatic():
        async with mysql_discard_database() as db:
            count = await discard_expired_product(1, NOW.date(), db)
            await db.commit()
            return count

    _, count = await asyncio.gather(manual(), automatic())
    assert count == 1
    async with mysql_discard_database() as db:
        assert (await db.get(Product, 1)).stock_quantity == 18
        assert await db.scalar(select(func.sum(InventoryDiscard.quantity))) == 22


async def test_mysql_discard_service_transaction_rollback():
    """只在现有库内开启可回滚事务，验证真实 SQL 和幂等响应，不改变演示库存。"""
    if os.getenv("RUN_MYSQL_TESTS") != "1":
        pytest.skip("set RUN_MYSQL_TESTS=1 to run transactional MySQL verification")
    from app.core.database import async_engine, async_session_factory
    from app.models.employee import Employee
    from app.models.enums import EmployeeRole

    async with async_session_factory() as db:
        db.info["defer_commit"] = True
        try:
            manager = await db.scalar(
                select(Employee).where(
                    Employee.role == EmployeeRole.STORE_MANAGER,
                    Employee.is_active.is_(True),
                    Employee.must_change_password.is_(False),
                )
            )
            if manager is None:
                pytest.skip("an enabled store manager is required")
            product = await db.scalar(
                select(Product)
                .where(
                    Product.store_id == manager.store_id,
                    Product.stock_quantity > 0,
                )
                .order_by(Product.id)
            )
            if product is None:
                pytest.skip("stocked product is required")
            initial = product.stock_quantity
            await context(db, manager.id, str(manager.store_id))
            req = payload(product_id=product.id, quantity=1)
            first = await create_discard(req, manager.id, db)
            repeated = await create_discard(req, manager.id, db)
            assert repeated.id == first.id
            assert (await db.get(Product, product.id)).stock_quantity == initial - 1
            assert first.items[0].after_quantity == first.items[0].before_quantity - 1
            product_id = product.id
        finally:
            await db.rollback()
    async with async_session_factory() as db:
        assert (await db.get(Product, product_id)).stock_quantity == initial
    await async_engine.dispose()
