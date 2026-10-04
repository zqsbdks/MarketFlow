"""Append varied half-year supermarket data to stores 2+, preserving existing records.

Run: python -m scripts.seed_store_scale_demo [--store-id ID]
Each store is one validated transaction with a completion marker; reruns skip it.
"""

import argparse
import asyncio
import random
import secrets
from collections import defaultdict
from datetime import datetime, time, timedelta
from decimal import Decimal

from sqlalchemy import func, insert, select, text

from app.core import store_policy  # noqa: F401 -- register background write-store stamping
from app.core.business_time import business_now
from app.core.database import async_engine, async_session_factory
from app.core.security import hash_password
from app.models.contact_notice import ContactNotice, ContactNoticeRecipient
from app.models.department import Department
from app.models.employee import Employee
from app.models.employee_detail import EmployeeDetail
from app.models.enums import (
    EmployeeRole,
    InventoryBatchStatus,
    ProductStatus,
    PurchaseStatus,
    SaleSource,
)
from app.models.inventory_batch import InventoryBatch
from app.models.operation_audit_log import OperationAuditLog
from app.models.product import Product
from app.models.purchase import Purchase
from app.models.purchase_item import PurchaseItem
from app.models.sale import Sale
from app.models.sale_item import SaleItem
from app.models.store import Store, StoreDepartment
from app.models.supplier import Supplier
from app.models.supplier_product import SupplierProduct
from scripts.seed_contact_notices import TEMPLATES
from scripts.seed_japanese_demo import (
    batch_status,
    create_discount_rules,
    discounted_unit_price,
    find_sale_discount,
    money,
)

MARKER = "store_scale_half_year_v1"


async def validate_store(db, store_id):
    """Check relational, financial and physical invariants before committing a store."""
    checks = {
        "sale_totals": """
          SELECT COUNT(*) FROM sale s JOIN (
            SELECT sale_id, SUM(subtotal) revenue, SUM(cost_subtotal) cost,
                   SUM(original_unit_price * quantity) original
            FROM sale_item WHERE store_id=:sid GROUP BY sale_id
          ) i ON i.sale_id=s.id WHERE s.store_id=:sid AND
          (s.total_amount<>i.revenue OR s.total_cost<>i.cost
           OR s.original_total_amount<>i.original
           OR s.gross_profit<>i.revenue-i.cost
           OR s.discount_amount<>i.original-i.revenue)""",
        "sale_time_and_store": """
          SELECT COUNT(*) FROM sale_item i JOIN sale s ON s.id=i.sale_id
          JOIN inventory_batch b ON b.id=i.inventory_batch_id
          JOIN product p ON p.id=i.product_id
          WHERE i.store_id=:sid AND (s.store_id<>i.store_id OR b.store_id<>i.store_id
          OR p.store_id<>i.store_id OR b.product_id<>i.product_id
          OR s.sold_at<b.arrived_at OR DATE(s.sold_at)>b.expiration_date
          OR i.subtotal<>i.unit_price*i.quantity OR i.cost_subtotal<>i.unit_cost*i.quantity
          OR i.discount_amount<>(i.original_unit_price-i.unit_price)*i.quantity)""",
        "batch_balance": """
          SELECT COUNT(*) FROM inventory_batch b LEFT JOIN (
            SELECT inventory_batch_id bid, SUM(quantity) qty
            FROM sale_item WHERE store_id=:sid GROUP BY inventory_batch_id
          ) i ON i.bid=b.id LEFT JOIN (
            SELECT a.target_id bid, SUM(CAST(JSON_UNQUOTE(JSON_EXTRACT(a.after_data,
                       '$.discarded_quantity')) AS UNSIGNED)) qty
            FROM operation_audit_log a WHERE a.store_id=:sid
            AND a.target_type='inventory_batch' AND a.action IN ('discard_expired','discard_manual')
            GROUP BY a.target_id
          ) d ON d.bid=b.id WHERE b.store_id=:sid
          AND (b.initial_quantity<>b.remaining_quantity+COALESCE(i.qty,0)+COALESCE(d.qty,0)
               OR b.remaining_quantity<0)""",
        "product_stock": """
          SELECT COUNT(*) FROM product p LEFT JOIN (
            SELECT product_id, SUM(remaining_quantity) qty FROM inventory_batch
            WHERE store_id=:sid GROUP BY product_id
          ) b ON b.product_id=p.id WHERE p.store_id=:sid
          AND p.stock_quantity<>COALESCE(b.qty,0)""",
        "purchase_totals": """
          SELECT COUNT(*) FROM purchase p JOIN (
            SELECT purchase_id, SUM(subtotal) amount FROM purchase_item
            WHERE store_id=:sid GROUP BY purchase_id
          ) i ON i.purchase_id=p.id WHERE p.store_id=:sid AND p.total_amount<>i.amount""",
        "batch_purchase_store": """
          SELECT COUNT(*) FROM inventory_batch b JOIN purchase_item i ON i.id=b.purchase_item_id
          JOIN purchase p ON p.id=i.purchase_id WHERE b.store_id=:sid
          AND (i.store_id<>b.store_id OR p.store_id<>b.store_id OR i.product_id<>b.product_id
               OR p.status<>'arrived' OR b.initial_quantity<>i.quantity)""",
        "discount_store": """
          SELECT COUNT(*) FROM discount_rule_scope sc
          JOIN discount_rule r ON r.id=sc.discount_rule_id
          JOIN product p ON p.id=sc.product_id WHERE r.store_id=:sid
          AND (sc.store_id<>r.store_id OR p.store_id<>r.store_id)""",
    }
    results = {}
    for name, sql in checks.items():
        failures = int(await db.scalar(text(sql), {"sid": store_id}) or 0)
        results[name] = failures
        if failures:
            raise RuntimeError(f"Store {store_id}: {name} has {failures} inconsistent records")
    return results


async def master_data(db, store, departments, rng, start):
    source = (
        await db.execute(
            select(Product, SupplierProduct, Supplier)
            .join(SupplierProduct, Product.supplier_product_id == SupplierProduct.id)
            .join(Supplier, SupplierProduct.supplier_id == Supplier.id)
            .where(Product.store_id == 1)
            .order_by(Product.id)
        )
    ).all()
    employees = list(
        (await db.scalars(select(Employee).where(Employee.store_id == store.id))).all()
    )
    manager = next(e for e in employees if e.role == EmployeeRole.STORE_MANAGER)
    for department in departments.values():
        config = await db.get(StoreDepartment, (store.id, department.id))
        if config is None:
            db.add(StoreDepartment(store_id=store.id, department_id=department.id, is_active=True))
        else:
            config.is_active = True
        # Ensure every department has a responsible employee and a part-time member.
        for role in (EmployeeRole.REGULAR_EMPLOYEE, EmployeeRole.CONTRACT_WORKER):
            if any(e.department_id == department.id and e.role == role for e in employees):
                continue
            employee = Employee(
                employee_no=f"DS{store.id:02d}-{department.id}-{role.name[:3]}",
                name=department.name
                + (" 担当" if role == EmployeeRole.REGULAR_EMPLOYEE else " 補助"),
                role=role,
                store_id=store.id,
                department_id=department.id,
                password_hash=hash_password(secrets.token_urlsafe(24)),
                must_change_password=True,
                detail=EmployeeDetail(hire_date=start - timedelta(days=rng.randint(30, 200))),
            )
            db.add(employee)
            employees.append(employee)
    await db.flush()
    products, catalog_by_product = [], {}
    price_factor = Decimal(str(round(rng.uniform(0.93, 1.09), 3)))
    for original, source_catalog, source_supplier in source:
        supplier = await db.scalar(
            select(Supplier).where(
                Supplier.store_id == store.id, Supplier.name == source_supplier.name
            )
        )
        if supplier is None:
            supplier = Supplier(
                store_id=store.id,
                supplier_no=f"DS{store.id:02d}-SUP{source_supplier.id}",
                name=source_supplier.name,
                contact_name=source_supplier.contact_name,
                phone=source_supplier.phone,
                address=source_supplier.address,
                is_active=True,
            )
            db.add(supplier)
            await db.flush()
        catalog = await db.scalar(
            select(SupplierProduct).where(
                SupplierProduct.store_id == store.id,
                SupplierProduct.supplier_id == supplier.id,
                SupplierProduct.name == source_catalog.name,
            )
        )
        if catalog is None:
            catalog = SupplierProduct(
                store_id=store.id,
                supplier_id=supplier.id,
                category_id=source_catalog.category_id,
                name=source_catalog.name,
                unit_cost=money(source_catalog.unit_cost * price_factor),
                shelf_life_days=source_catalog.shelf_life_days,
                is_active=True,
            )
            db.add(catalog)
            await db.flush()
        product = await db.scalar(
            select(Product).where(
                Product.store_id == store.id, Product.supplier_product_id == catalog.id
            )
        )
        if product is None:
            product = Product(
                store_id=store.id,
                product_no=f"DS{store.id:02d}-P{original.id:05d}",
                name=original.name,
                supplier_product_id=catalog.id,
                department_id=original.department_id,
                category_id=original.category_id,
                purchase_price=catalog.unit_cost,
                sale_price=money(
                    original.sale_price
                    * price_factor
                    * Decimal(str(round(rng.uniform(0.97, 1.05), 3)))
                ),
                stock_quantity=0,
                expiry_warning_days=original.expiry_warning_days,
                low_stock_threshold=rng.randint(5, 12),
                status=ProductStatus.ON_SALE,
            )
            db.add(product)
            await db.flush()
        products.append(product)
        catalog_by_product[product.id] = (catalog, supplier)
    return manager, employees, products, catalog_by_product


async def purchases(db, store, manager, products, catalogs, start, now, rng, volume):
    by_department = defaultdict(list)
    for product in products:
        by_department[product.department_id].append(product)
    ledgers = defaultdict(list)
    day = start
    counter = 0
    while day <= now.date() + timedelta(days=2):
        new_logs = []
        for department_id, choices in by_department.items():
            # Daily fresh-food replenishment; occasional skipped deliveries or extra lots.
            if rng.random() < 0.06:
                continue
            arrival = datetime.combine(day, time(8, rng.randint(0, 40)))
            ordered = datetime.combine(day - timedelta(days=2), time(9, rng.randint(0, 50)))
            arrived = arrival <= now
            selected = rng.sample(choices, rng.choices([3, 4, 5], [15, 65, 20])[0])
            counter += 1
            purchase = Purchase(
                store_id=store.id,
                purchase_no=f"DS{store.id:02d}-PO{counter:06d}",
                department_id=department_id,
                created_by=manager.id,
                received_by=manager.id if arrived else None,
                ordered_at=ordered,
                expected_arrival_at=arrival,
                arrived_at=arrival if arrived else None,
                total_amount=Decimal("0"),
                status=PurchaseStatus.ARRIVED if arrived else PurchaseStatus.PENDING,
                created_at=ordered,
                updated_at=arrival if arrived else ordered,
            )
            db.add(purchase)
            await db.flush()
            for index, product in enumerate(selected):
                catalog, supplier = catalogs[product.id]
                quantity = max(12, round(rng.randint(24, 40) * volume))
                cost = money(
                    product.purchase_price * Decimal(str(rng.choice([0.96, 0.98, 1, 1.02, 1.04])))
                )
                shelf_life = catalog.shelf_life_days or 7
                production = day - timedelta(days=rng.randint(0, min(2, shelf_life - 1)))
                expiry = production + timedelta(days=shelf_life)
                line = PurchaseItem(
                    store_id=store.id,
                    purchase_id=purchase.id,
                    product_id=product.id,
                    supplier_product_id=catalog.id,
                    supplier_id=supplier.id,
                    product_no_snapshot=product.product_no,
                    product_name_snapshot=product.name,
                    supplier_name_snapshot=supplier.name,
                    quantity=quantity,
                    unit_cost=cost,
                    subtotal=money(cost * quantity),
                    production_date=production,
                    expiration_date=expiry,
                    created_at=ordered,
                )
                db.add(line)
                await db.flush()
                purchase.total_amount += line.subtotal
                if not arrived:
                    continue
                batch = InventoryBatch(
                    store_id=store.id,
                    batch_no=f"DS{store.id:02d}-LOT{counter:06d}-{index}",
                    product_id=product.id,
                    purchase_item_id=line.id,
                    production_date=production,
                    expiration_date=expiry,
                    initial_quantity=quantity,
                    remaining_quantity=quantity,
                    status=InventoryBatchStatus.AVAILABLE,
                    arrived_at=arrival,
                    created_at=arrival,
                    updated_at=arrival,
                )
                db.add(batch)
                await db.flush()
                ledgers[product.id].append((batch, cost))
                new_logs.append(
                    dict(
                        store_id=store.id,
                        employee_id=manager.id,
                        module="inventory",
                        action="create_batch",
                        target_type="inventory_batch",
                        target_id=batch.id,
                        before_data=None,
                        after_data={
                            "batch_no": batch.batch_no,
                            "product_id": product.id,
                            "purchase_item_id": line.id,
                            "remaining_quantity": quantity,
                            "expiration_date": expiry.isoformat(),
                            "status": "available",
                        },
                        reason="入荷検収による在庫追加",
                        created_at=arrival,
                    )
                )
        if new_logs:
            await db.execute(insert(OperationAuditLog), new_logs)
        day += timedelta(days=1)
    for lots in ledgers.values():
        lots.sort(key=lambda lot: (lot[0].expiration_date, lot[0].arrived_at, lot[0].id))
    return ledgers, counter


async def sales(db, store, products, ledgers, rules, departments, start, now, rng, volume):
    codes = {department.id: code for code, department in departments.items()}
    # Persistent local preferences produce genuinely different rankings at each store.
    preference = {p.id: rng.uniform(0.65, 1.5) for p in products}
    counter = 0
    day = start
    while day <= now.date():
        weekend = 1.22 if day.isoweekday() >= 6 else 0.93
        seasonal = 1 + 0.08 * ((day.month + store.id) % 3 - 1)
        count = max(1, round(rng.randint(82, 103) * weekend * seasonal * volume))
        moments = sorted(
            datetime.combine(
                day,
                time(
                    rng.choices(
                        [9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20],
                        [5, 6, 8, 12, 8, 6, 6, 8, 13, 14, 10, 4],
                    )[0],
                    rng.randrange(60),
                    rng.randrange(60),
                ),
            )
            for _ in range(count)
        )
        lots_today = {
            p.id: [
                (b, c) for b, c in ledgers[p.id] if b.arrived_at.date() <= day <= b.expiration_date
            ]
            for p in products
        }
        daily = []
        for moment in moments:
            if moment > now:
                continue
            available = [
                p
                for p in products
                if any(
                    b.remaining_quantity > 0 and b.arrived_at <= moment for b, _ in lots_today[p.id]
                )
            ]
            if not available:
                continue
            selected = []
            for _ in range(min(rng.randint(1, 4), len(available))):
                product = rng.choices(available, [preference[p.id] for p in available])[0]
                available.remove(product)
                selected.append(product)
            items, logs = [], []
            for product in selected:
                requested = rng.choices([1, 2, 3, 4], [55, 29, 12, 4])[0]
                rule = find_sale_discount(product, moment, rules, codes)
                price = discounted_unit_price(product, rule)
                for batch, cost in lots_today[product.id]:
                    if requested == 0:
                        break
                    if batch.remaining_quantity == 0 or batch.arrived_at > moment:
                        continue
                    before = batch.remaining_quantity
                    quantity = min(requested, before)
                    batch.remaining_quantity -= quantity
                    batch.updated_at = moment
                    requested -= quantity
                    item = dict(
                        store_id=store.id,
                        product_id=product.id,
                        inventory_batch_id=batch.id,
                        product_no_snapshot=product.product_no,
                        product_name_snapshot=product.name,
                        department_id=product.department_id,
                        quantity=quantity,
                        original_unit_price=product.sale_price,
                        unit_price=price,
                        discount_amount=money((product.sale_price - price) * quantity),
                        discount_rule_id=rule.id if rule else None,
                        discount_rule_name_snapshot=rule.name if rule else None,
                        discount_type_snapshot=rule.discount_type.value if rule else None,
                        discount_value_snapshot=rule.discount_value if rule else None,
                        unit_cost=cost,
                        subtotal=money(price * quantity),
                        cost_subtotal=money(cost * quantity),
                        created_at=moment,
                    )
                    items.append(item)
                    logs.append(
                        dict(
                            store_id=store.id,
                            employee_id=None,
                            module="inventory",
                            action="sale_deduction",
                            target_type="inventory_batch",
                            target_id=batch.id,
                            before_data={"remaining_quantity": before},
                            after_data={
                                "remaining_quantity": batch.remaining_quantity,
                                "deducted_quantity": quantity,
                                "status": "sold_out"
                                if batch.remaining_quantity == 0
                                else "available",
                            },
                            reason="POSレジ販売による在庫減少",
                            created_at=moment,
                        )
                    )
            if not items:
                continue
            counter += 1
            total = money(sum(i["subtotal"] for i in items))
            original = money(sum(i["original_unit_price"] * i["quantity"] for i in items))
            cost = money(sum(i["cost_subtotal"] for i in items))
            sale = Sale(
                store_id=store.id,
                sale_no=f"DS{store.id:02d}-S{counter:07d}",
                sold_at=moment,
                original_total_amount=original,
                discount_amount=original - total,
                total_amount=total,
                total_cost=cost,
                gross_profit=total - cost,
                source=SaleSource.DEMO_SEED,
                created_at=moment,
            )
            db.add(sale)
            daily.append((sale, items, logs))
        await db.flush()
        rows, audit = [], []
        for sale, items, logs in daily:
            rows.extend(dict(item, sale_id=sale.id) for item in items)
            for log in logs:
                log["after_data"]["sale_id"] = sale.id
                audit.append(log)
        if rows:
            await db.execute(insert(SaleItem), rows, execution_options={"render_nulls": True})
            await db.execute(insert(OperationAuditLog), audit)
        day += timedelta(days=1)
    return counter


async def notices(db, store, manager, employees, departments, start, now, rng):
    count = 0
    day = start
    while day <= now.date():
        groups = [("all", None, employees)]
        groups.extend(
            ("department", d.id, [e for e in employees if e.department_id == d.id])
            for d in departments.values()
        )
        groups.append(("personal", None, rng.sample(employees, min(2, len(employees)))))
        for target, department_id, recipients in groups:
            title, content, priority, _, _ = rng.choice(TEMPLATES)
            created = datetime.combine(day, time(8, rng.randrange(45)))
            deadline = created + timedelta(days=rng.choice([1, 2, 3]))
            status = "closed" if deadline < now else "published"
            if rng.random() < 0.08:
                status = rng.choice(["draft", "withdrawn"])
            notice = ContactNotice(
                store_id=store.id,
                source="store",
                publisher_id=manager.id,
                title=f"{title} ({day:%m/%d})",
                content=content,
                priority=priority,
                target_type=target,
                department_id=department_id,
                starts_at=created,
                deadline_at=deadline,
                close_on_all_confirmed=True,
                status=status,
                closed_at=deadline if status == "closed" else None,
                close_reason="deadline_passed" if status == "closed" else None,
                created_at=created,
                updated_at=deadline if status == "closed" else created,
            )
            db.add(notice)
            await db.flush()
            if status in ("published", "closed"):
                for employee in recipients:
                    read = created + timedelta(minutes=rng.randint(20, 80))
                    confirm = read + timedelta(minutes=rng.randint(5, 90))
                    if status != "closed" and (confirm > now or rng.random() < 0.35):
                        confirm = None
                    if read > now:
                        read = None
                    db.add(
                        ContactNoticeRecipient(
                            store_id=store.id,
                            notice_id=notice.id,
                            employee_id=employee.id,
                            read_at=read,
                            confirmed_at=confirm,
                            created_at=created,
                        )
                    )
            count += 1
        day += timedelta(days=1)
    return count


async def seed_store(store_id):
    now = business_now().replace(microsecond=0)
    async with async_session_factory() as db:
        store = await db.get(Store, store_id)
        if store is None or store.id == 1:
            raise RuntimeError("Only additional existing stores may be populated")
        if await db.scalar(
            select(OperationAuditLog.id)
            .where(OperationAuditLog.store_id == store.id, OperationAuditLog.action == MARKER)
            .limit(1)
        ):
            print(f"{store.store_no}: already complete; skipped", flush=True)
            return
        start = (await db.scalar(select(func.min(Sale.sold_at)).where(Sale.store_id == 1))).date()
        rng = random.Random(2026100400 + store.id)
        volume = rng.uniform(0.88, 1.17)
        departments = {
            d.code: d
            for d in (
                await db.scalars(select(Department).where(Department.is_active.is_(True)))
            ).all()
        }
        manager, employees, products, catalogs = await master_data(
            db, store, departments, rng, start
        )
        db.info["write_store_id"] = store.id
        rules = await create_discount_rules(db, manager, departments, products, now.date())
        for code in departments:
            rules[code].discount_value = Decimal(
                str(
                    rng.choice(
                        {
                            "PRODUCE": [0.88, 0.9, 0.92],
                            "MEAT": [0.83, 0.85, 0.88],
                            "SEAFOOD": [0.75, 0.8, 0.85],
                            "DELI": [0.65, 0.7, 0.75],
                        }[code]
                    )
                )
            )
            percent_off = round((1 - rules[code].discount_value) * 100)
            rules[code].name = f"{departments[code].name} 時間帯セール{percent_off}％OFF"
        await db.flush()
        print(f"{store.store_no}: generating purchases and batches...", flush=True)
        ledgers, purchase_count = await purchases(
            db, store, manager, products, catalogs, start, now, rng, volume
        )
        print(f"{store.store_no}: generating chronological sales...", flush=True)
        sale_count = await sales(
            db, store, products, ledgers, rules, departments, start, now, rng, volume
        )
        for product in products:
            for batch, _ in ledgers[product.id]:
                batch.status = batch_status(batch, product, now.date())
            await db.flush()
            product.stock_quantity = int(
                await db.scalar(
                    select(func.sum(InventoryBatch.remaining_quantity)).where(
                        InventoryBatch.product_id == product.id
                    )
                )
                or 0
            )
        notice_count = await notices(db, store, manager, employees, departments, start, now, rng)
        await db.flush()
        # Every generated lot is exactly initial minus the linked sales, without negative stock.
        consumed = dict(
            (
                await db.execute(
                    select(SaleItem.inventory_batch_id, func.sum(SaleItem.quantity))
                    .where(SaleItem.store_id == store.id)
                    .group_by(SaleItem.inventory_batch_id)
                )
            ).all()
        )
        for lots in ledgers.values():
            for batch, _ in lots:
                if (
                    batch.initial_quantity - consumed.get(batch.id, 0) != batch.remaining_quantity
                    or batch.remaining_quantity < 0
                ):
                    raise RuntimeError(f"Inventory reconciliation failed: {batch.batch_no}")
        if sale_count < 14000:
            raise RuntimeError(f"Too few sales: {sale_count}; store transaction rolled back")
        validation = await validate_store(db, store.id)
        summary = {
            "products": len(products),
            "new_purchases": purchase_count,
            "new_sales": sale_count,
            "new_batches": sum(len(lots) for lots in ledgers.values()),
            "new_notices": notice_count,
            "random_seed": 2026100400 + store.id,
            "start": start.isoformat(),
            "end": now.isoformat(),
            "validation": validation,
        }
        db.add(
            OperationAuditLog(
                store_id=store.id,
                employee_id=manager.id,
                module="demo_seed",
                action=MARKER,
                target_type="store",
                target_id=store.id,
                after_data=summary,
                reason="半年的门店规模随机业务演示数据",
            )
        )
        await db.commit()
        print(f"{store.store_no}: committed {summary}", flush=True)


async def finalize_store(store_id):
    """Discard old unsold perishables, retaining recent exceptions for the stock workflow."""
    now = business_now().replace(microsecond=0)
    async with async_session_factory() as db:
        if not await db.scalar(
            select(OperationAuditLog.id)
            .where(OperationAuditLog.store_id == store_id, OperationAuditLog.action == MARKER)
            .limit(1)
        ):
            raise RuntimeError(f"Store {store_id} generation is incomplete")
        action = "store_scale_finalize_v1"
        if await db.scalar(
            select(OperationAuditLog.id)
            .where(OperationAuditLog.store_id == store_id, OperationAuditLog.action == action)
            .limit(1)
        ):
            return
        batches = list(
            (
                await db.scalars(
                    select(InventoryBatch).where(
                        InventoryBatch.store_id == store_id,
                        InventoryBatch.remaining_quantity > 0,
                        InventoryBatch.expiration_date < now.date() - timedelta(days=2),
                    )
                )
            ).all()
        )
        logs = []
        for batch in batches:
            quantity = batch.remaining_quantity
            logs.append(
                dict(
                    store_id=store_id,
                    employee_id=None,
                    module="inventory",
                    action="discard_expired",
                    target_type="inventory_batch",
                    target_id=batch.id,
                    before_data={"remaining_quantity": quantity, "status": "expired"},
                    after_data={
                        "remaining_quantity": 0,
                        "status": "sold_out",
                        "discarded_quantity": quantity,
                    },
                    reason="期限切れ商品の定期廃棄",
                    created_at=max(
                        batch.arrived_at,
                        datetime.combine(batch.expiration_date + timedelta(days=1), time(8, 50)),
                    ),
                )
            )
            batch.remaining_quantity = 0
            batch.status = InventoryBatchStatus.SOLD_OUT
        await db.flush()
        if logs:
            await db.execute(insert(OperationAuditLog), logs)
        products = (await db.scalars(select(Product).where(Product.store_id == store_id))).all()
        for product in products:
            product.stock_quantity = int(
                await db.scalar(
                    select(func.sum(InventoryBatch.remaining_quantity)).where(
                        InventoryBatch.product_id == product.id
                    )
                )
                or 0
            )
        notices = (
            await db.scalars(select(ContactNotice).where(ContactNotice.store_id == store_id))
        ).all()
        for notice in notices:
            notice.content = (
                notice.content.replace(
                    "全員の確認が完了したため、この連絡は終了しています。",
                    "値札の更新後は売場の表示とレジ登録価格を照合してください。",
                )
                .replace(
                    "来週の売場変更についての下書きです。公開前に担当者と作業内容を確認します。",
                    "来週の売場変更について担当者と作業内容を確認してください。",
                )
                .replace(
                    "作業予定を見直すため、この連絡は取り下げました。新しい予定は別途連絡します。",
                    "作業予定を見直します。新しい予定を確認し担当者間で共有してください。",
                )
            )
        await db.flush()
        await validate_store(db, store_id)
        db.add(
            OperationAuditLog(
                store_id=store_id,
                employee_id=None,
                module="demo_seed",
                action=action,
                target_type="store",
                target_id=store_id,
                after_data={
                    "discarded_batches": len(logs),
                    "discarded_quantity": sum(
                        row["after_data"]["discarded_quantity"] for row in logs
                    ),
                },
                reason="历史过期库存清理与联络内容一致性校验",
            )
        )
        await db.commit()
        print(f"Store {store_id}: finalized, discarded {len(logs)} old expired lots", flush=True)


async def main(store_id=None, workers=3):
    try:
        async with async_session_factory() as db:
            ids = list(
                (
                    await db.scalars(
                        select(Store.id)
                        .where(Store.id > 1, Store.is_active.is_(True))
                        .order_by(Store.id)
                    )
                ).all()
            )
        semaphore = asyncio.Semaphore(workers)

        async def run(item):
            async with semaphore:
                await seed_store(item)
                await finalize_store(item)

        results = await asyncio.gather(
            *(run(item) for item in ([store_id] if store_id else ids)),
            return_exceptions=True,
        )
        failures = [result for result in results if isinstance(result, BaseException)]
        if failures:
            raise RuntimeError(f"{len(failures)} store transactions failed: {failures}")
    finally:
        await async_engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--store-id", type=int)
    parser.add_argument("--workers", type=int, choices=range(1, 5), default=3)
    arguments = parser.parse_args()
    asyncio.run(main(arguments.store_id, arguments.workers))
