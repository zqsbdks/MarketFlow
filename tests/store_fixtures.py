"""Isolated two-store database; never connects to the configured demonstration database."""

import json
from decimal import Decimal

from sqlalchemy import BigInteger, DefaultClause, Integer, MetaData, event, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.database import MarketFlowSession
from app.models import Base
from app.models.category import Category
from app.models.department import Department
from app.models.employee import Employee
from app.models.enums import EmployeeRole, ProductStatus
from app.models.product import Product
from app.models.store import Store, StoreDepartment
from app.models.supplier import Supplier
from app.models.supplier_product import SupplierProduct


async def create_store_database(url="sqlite+aiosqlite:///:memory:"):
    engine = create_async_engine(url)
    sqlite = engine.dialect.name == "sqlite"

    @event.listens_for(engine.sync_engine, "connect")
    def add_json_contains(connection, _):
        if not sqlite:
            return
        # The application uses MySQL JSON_CONTAINS for weekly discount schedules.
        connection.create_function(
            "json_contains",
            2,
            lambda document, value: (
                int(json.loads(value) in (json.loads(document) or [])) if document else 0
            ),
        )

    # SQLite autoincrement requires INTEGER exactly. Keep production/MySQL metadata intact.
    metadata = MetaData()
    for table in Base.metadata.sorted_tables:
        table.to_metadata(metadata)
    for table in metadata.tables.values():
        for column in table.columns:
            if sqlite and isinstance(column.type, BigInteger):
                column.type = Integer()
            if (
                sqlite
                and column.server_default is not None
                and "ON UPDATE" in str(column.server_default.arg)
            ):
                column.server_default = DefaultClause(text("CURRENT_TIMESTAMP"))
    async with engine.begin() as connection:
        await connection.run_sync(metadata.create_all)
    factory = async_sessionmaker(engine, class_=MarketFlowSession, expire_on_commit=False)
    async with factory() as db:
        db.add_all([Store(id=i, store_no=f"DP{i:04d}", name=f"Store {i}") for i in (1, 2)])
        db.add_all([Department(id=i, code=f"D{i}", name=f"Department {i}") for i in (1, 2)])
        await db.flush()
        db.add_all([Category(id=i, department_id=i, name=f"Category {i}") for i in (1, 2)])
        await db.flush()
        for store in (1, 2):
            db.add(StoreDepartment(store_id=store, department_id=1, is_active=True))
            db.add(
                Supplier(
                    id=store, store_id=store, supplier_no=f"SUP{store}", name=f"Supplier {store}"
                )
            )
            await db.flush()
            db.add(
                SupplierProduct(
                    id=store,
                    store_id=store,
                    supplier_id=store,
                    category_id=1,
                    name=f"Catalog {store}",
                    unit_cost=Decimal("5"),
                    shelf_life_days=7,
                )
            )
            await db.flush()
            db.add(
                Product(
                    id=store,
                    store_id=store,
                    product_no=f"P{store}",
                    name=f"Product {store}",
                    supplier_product_id=store,
                    department_id=1,
                    category_id=1,
                    purchase_price=Decimal("5"),
                    sale_price=Decimal("10"),
                    stock_quantity=0,
                    status=ProductStatus.ON_SALE,
                )
            )
        roles = [
            EmployeeRole.STORE_MANAGER,
            EmployeeRole.REGULAR_EMPLOYEE,
            EmployeeRole.CONTRACT_WORKER,
            EmployeeRole.HEADQUARTERS,
            EmployeeRole.REGULAR_EMPLOYEE,
        ]
        for id_, role in enumerate(roles, 1):
            headquarters = role == EmployeeRole.HEADQUARTERS
            db.add(
                Employee(
                    id=id_,
                    employee_no=f"EMP{id_}",
                    name=f"Employee {id_}",
                    password_hash="test-only",
                    role=role,
                    store_id=None if headquarters else (2 if id_ == 5 else 1),
                    department_id=None if headquarters or role == EmployeeRole.STORE_MANAGER else 1,
                    is_active=True,
                    must_change_password=False,
                )
            )
        await db.commit()
    return engine, factory
