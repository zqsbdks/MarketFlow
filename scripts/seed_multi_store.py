"""给已有的 1 号店演示库追加 29 家日本门店及两个月的业务样本。

脚本可重复执行：已有编号的门店和已生成的商品不会再次插入。初始密码只在
第一次生成账号时打印，不写入文件或仓库。请仅在演示环境运行。
"""

# ruff: noqa: E402
import asyncio
import secrets
import sys
from datetime import timedelta
from decimal import Decimal
from io import TextIOWrapper
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
if isinstance(sys.stdout, TextIOWrapper):
    sys.stdout.reconfigure(encoding="utf-8")

from sqlalchemy import func, select

from app.core.business_time import business_now
from app.core.database import async_engine, async_session_factory
from app.core.security import hash_password
from app.models.contact_notice import ContactNotice, ContactNoticeRecipient
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

CITIES = [
    ("札幌駅前", "北海道札幌市中央区"),
    ("函館", "北海道函館市"),
    ("仙台中央", "宮城県仙台市青葉区"),
    ("盛岡", "岩手県盛岡市"),
    ("秋田", "秋田県秋田市"),
    ("郡山", "福島県郡山市"),
    ("宇都宮", "栃木県宇都宮市"),
    ("高崎", "群馬県高崎市"),
    ("大宮", "埼玉県さいたま市"),
    ("千葉中央", "千葉県千葉市"),
    ("船橋", "千葉県船橋市"),
    ("新宿", "東京都新宿区"),
    ("渋谷", "東京都渋谷区"),
    ("品川", "東京都港区"),
    ("立川", "東京都立川市"),
    ("横浜", "神奈川県横浜市"),
    ("川崎", "神奈川県川崎市"),
    ("藤沢", "神奈川県藤沢市"),
    ("新潟", "新潟県新潟市"),
    ("長野", "長野県長野市"),
    ("静岡", "静岡県静岡市"),
    ("浜松", "静岡県浜松市"),
    ("名古屋", "愛知県名古屋市"),
    ("京都", "京都府京都市"),
    ("大阪梅田", "大阪府大阪市北区"),
    ("神戸三宮", "兵庫県神戸市"),
    ("広島", "広島県広島市"),
    ("福岡天神", "福岡県福岡市"),
    ("那覇", "沖縄県那覇市"),
]
SURNAMES = ["田中", "佐藤", "鈴木", "高橋", "渡辺", "伊藤", "山本", "中村", "小林", "加藤"]


def temporary_password():
    return "MF-" + secrets.token_urlsafe(15)


async def create_employee(db, *, name, role, store_id, department_id, password_hash, hire_date):
    employee = Employee(
        employee_no="TMP-" + uuid4().hex[:15],
        name=name,
        role=role,
        store_id=store_id,
        department_id=department_id,
        password_hash=password_hash,
        must_change_password=True,
        detail=EmployeeDetail(hire_date=hire_date),
    )
    db.add(employee)
    await db.flush()
    employee.employee_no = "HQ00001" if role == EmployeeRole.HEADQUARTERS else f"E{employee.id:05d}"
    return employee


async def seed():
    now = business_now().replace(microsecond=0)
    async with async_session_factory() as db:
        first = await db.get(Store, 1)
        if first is None or first.store_no != "DP0001":
            raise RuntimeError("1 号店必须先存在且编号为 DP0001，请先运行数据库迁移")
        department_ids = list(
            (
                await db.scalars(
                    select(StoreDepartment.department_id).where(
                        StoreDepartment.store_id == 1, StoreDepartment.is_active.is_(True)
                    )
                )
            ).all()
        )
        source = (
            await db.execute(
                select(Product, SupplierProduct, Supplier)
                .join(SupplierProduct, Product.supplier_product_id == SupplierProduct.id)
                .join(Supplier, SupplierProduct.supplier_id == Supplier.id)
                .where(Product.store_id == 1)
                .order_by(Product.id)
            )
        ).all()
        if not source or not department_ids:
            raise RuntimeError("1 号店需要已有统一部门及供应商商品演示数据")

        hq_password = None
        hq = await db.scalar(select(Employee).where(Employee.employee_no == "HQ00001"))
        if hq is None:
            hq_password = temporary_password()
            await create_employee(
                db,
                name="本部管理者",
                role=EmployeeRole.HEADQUARTERS,
                store_id=None,
                department_id=None,
                password_hash=hash_password(hq_password),
                hire_date=now.date() - timedelta(days=90),
            )

        staff_password = temporary_password()
        staff_hash = hash_password(staff_password)
        created_stores = 0
        created_staff = 0
        for offset, (city, address) in enumerate(CITIES, start=2):
            store_no = f"DP{offset:04d}"
            store = await db.scalar(select(Store).where(Store.store_no == store_no))
            if store is None:
                store = Store(
                    store_no=store_no,
                    name=f"MarketFlow {city}店",
                    address=address,
                    phone=f"03-9000-{offset:04d}" if "東京" in address else None,
                    timezone="Asia/Tokyo",
                    is_active=True,
                )
                db.add(store)
                await db.flush()
                created_stores += 1
            if store.id != offset:
                raise RuntimeError(f"{store_no} 的数据库ID不是 {offset}，停止以避免错配")
            enabled = department_ids[: 2 + (offset % 3)]
            for department_id in enabled:
                config = await db.get(StoreDepartment, (store.id, department_id))
                if config is None:
                    db.add(
                        StoreDepartment(
                            store_id=store.id, department_id=department_id, is_active=True
                        )
                    )
            manager = await db.scalar(
                select(Employee)
                .where(Employee.store_id == store.id, Employee.role == EmployeeRole.STORE_MANAGER)
                .limit(1)
            )
            if manager is None:
                manager = await create_employee(
                    db,
                    name=f"{SURNAMES[offset % len(SURNAMES)]} 店長",
                    role=EmployeeRole.STORE_MANAGER,
                    store_id=store.id,
                    department_id=None,
                    password_hash=staff_hash,
                    hire_date=now.date() - timedelta(days=80),
                )
                created_staff += 1
            for department_id in enabled:
                member = await db.scalar(
                    select(Employee)
                    .where(
                        Employee.store_id == store.id,
                        Employee.department_id == department_id,
                        Employee.role == EmployeeRole.REGULAR_EMPLOYEE,
                    )
                    .limit(1)
                )
                if member is None:
                    await create_employee(
                        db,
                        name=f"{SURNAMES[(offset + department_id) % len(SURNAMES)]} 担当",
                        role=EmployeeRole.REGULAR_EMPLOYEE,
                        store_id=store.id,
                        department_id=department_id,
                        password_hash=staff_hash,
                        hire_date=now.date() - timedelta(days=70),
                    )
                    created_staff += 1
            contract = await db.scalar(
                select(Employee)
                .where(Employee.store_id == store.id, Employee.role == EmployeeRole.CONTRACT_WORKER)
                .limit(1)
            )
            if contract is None:
                await create_employee(
                    db,
                    name=f"{SURNAMES[(offset + 3) % len(SURNAMES)]} アルバイト",
                    role=EmployeeRole.CONTRACT_WORKER,
                    store_id=store.id,
                    department_id=enabled[0],
                    password_hash=staff_hash,
                    hire_date=now.date() - timedelta(days=30),
                )
                created_staff += 1

            if await db.scalar(select(func.count(Product.id)).where(Product.store_id == store.id)):
                continue
            chosen = []
            by_department = {department_id: 0 for department_id in enabled}
            for original, catalog, supplier in source:
                if (
                    original.department_id in by_department
                    and by_department[original.department_id] < 3
                ):
                    chosen.append((original, catalog, supplier))
                    by_department[original.department_id] += 1
            local_suppliers = {}
            for index, (original, catalog, supplier) in enumerate(chosen):
                local_supplier = local_suppliers.get(supplier.id)
                if local_supplier is None:
                    local_supplier = await db.scalar(
                        select(Supplier).where(
                            Supplier.store_id == store.id, Supplier.name == supplier.name
                        )
                    )
                    if local_supplier is None:
                        local_supplier = Supplier(
                            store_id=store.id,
                            supplier_no="TMP" + uuid4().hex[:16],
                            name=supplier.name,
                            contact_name=supplier.contact_name,
                            phone=supplier.phone,
                            address=supplier.address,
                            is_active=supplier.is_active,
                        )
                        db.add(local_supplier)
                        await db.flush()
                        local_supplier.supplier_no = f"SUP{local_supplier.id:05d}"
                    local_suppliers[supplier.id] = local_supplier
                local_catalog = await db.scalar(
                    select(SupplierProduct).where(
                        SupplierProduct.store_id == store.id,
                        SupplierProduct.supplier_id == local_supplier.id,
                        SupplierProduct.name == catalog.name,
                    )
                )
                if local_catalog is None:
                    local_catalog = SupplierProduct(
                        store_id=store.id,
                        supplier_id=local_supplier.id,
                        category_id=catalog.category_id,
                        name=catalog.name,
                        unit_cost=catalog.unit_cost,
                        shelf_life_days=catalog.shelf_life_days,
                        is_active=catalog.is_active,
                    )
                    db.add(local_catalog)
                    await db.flush()
                product = Product(
                    store_id=store.id,
                    product_no="TMP-" + uuid4().hex[:15],
                    name=original.name,
                    supplier_product_id=local_catalog.id,
                    department_id=original.department_id,
                    category_id=original.category_id,
                    purchase_price=original.purchase_price,
                    sale_price=original.sale_price,
                    stock_quantity=0,
                    expiry_warning_days=original.expiry_warning_days,
                    low_stock_threshold=original.low_stock_threshold,
                    status=ProductStatus.ON_SALE,
                )
                db.add(product)
                await db.flush()
                product.product_no = f"P{product.id:05d}"
                # 每周一张历史小额进货与一张销售单，覆盖约两个月。
                for week in range(8):
                    arrival = now - timedelta(days=56 - week * 7, hours=2)
                    quantity = 4
                    sold = 2
                    purchase = Purchase(
                        store_id=store.id,
                        purchase_no="TMP-" + uuid4().hex[:20],
                        department_id=product.department_id,
                        created_by=manager.id,
                        received_by=manager.id,
                        ordered_at=arrival - timedelta(days=2),
                        expected_arrival_at=arrival,
                        arrived_at=arrival,
                        total_amount=catalog.unit_cost * quantity,
                        status=PurchaseStatus.ARRIVED,
                    )
                    db.add(purchase)
                    await db.flush()
                    purchase.purchase_no = f"PO{purchase.id:08d}"
                    expiry = arrival.date() + timedelta(days=catalog.shelf_life_days or 7)
                    line = PurchaseItem(
                        store_id=store.id,
                        purchase_id=purchase.id,
                        product_id=product.id,
                        supplier_product_id=local_catalog.id,
                        supplier_id=local_supplier.id,
                        product_no_snapshot=product.product_no,
                        product_name_snapshot=product.name,
                        supplier_name_snapshot=supplier.name,
                        quantity=quantity,
                        unit_cost=catalog.unit_cost,
                        subtotal=catalog.unit_cost * quantity,
                        production_date=arrival.date(),
                        expiration_date=expiry,
                    )
                    db.add(line)
                    await db.flush()
                    history_status = (
                        InventoryBatchStatus.EXPIRED
                        if expiry < now.date()
                        else InventoryBatchStatus.AVAILABLE
                    )
                    batch = InventoryBatch(
                        store_id=store.id,
                        batch_no="TMP-" + uuid4().hex[:20],
                        product_id=product.id,
                        purchase_item_id=line.id,
                        production_date=arrival.date(),
                        expiration_date=expiry,
                        initial_quantity=quantity,
                        remaining_quantity=quantity - sold,
                        status=history_status,
                        arrived_at=arrival,
                    )
                    db.add(batch)
                    await db.flush()
                    batch.batch_no = f"BAT{batch.id:08d}"
                    sold_at = arrival + timedelta(minutes=40)
                    price = original.sale_price
                    cost = catalog.unit_cost
                    sale = Sale(
                        store_id=store.id,
                        sale_no="TMP-" + uuid4().hex[:20],
                        sold_at=sold_at,
                        original_total_amount=price * sold,
                        discount_amount=Decimal("0.00"),
                        total_amount=price * sold,
                        total_cost=cost * sold,
                        gross_profit=(price - cost) * sold,
                        source=SaleSource.DEMO_SEED,
                    )
                    db.add(sale)
                    await db.flush()
                    sale.sale_no = f"S{sale.id:010d}"
                    db.add(
                        SaleItem(
                            store_id=store.id,
                            sale_id=sale.id,
                            product_id=product.id,
                            inventory_batch_id=batch.id,
                            product_no_snapshot=product.product_no,
                            product_name_snapshot=product.name,
                            department_id=product.department_id,
                            quantity=sold,
                            original_unit_price=price,
                            unit_price=price,
                            discount_amount=Decimal("0.00"),
                            unit_cost=cost,
                            subtotal=price * sold,
                            cost_subtotal=cost * sold,
                        )
                    )
                current_arrival = now - timedelta(hours=6)
                current_quantity = 25 + (store.id + index) % 21
                latest = Purchase(
                    store_id=store.id,
                    purchase_no="TMP-" + uuid4().hex[:20],
                    department_id=product.department_id,
                    created_by=manager.id,
                    received_by=manager.id,
                    ordered_at=current_arrival - timedelta(days=2),
                    expected_arrival_at=current_arrival,
                    arrived_at=current_arrival,
                    total_amount=catalog.unit_cost * current_quantity,
                    status=PurchaseStatus.ARRIVED,
                )
                db.add(latest)
                await db.flush()
                latest.purchase_no = f"PO{latest.id:08d}"
                latest_line = PurchaseItem(
                    store_id=store.id,
                    purchase_id=latest.id,
                    product_id=product.id,
                    supplier_product_id=local_catalog.id,
                    supplier_id=local_supplier.id,
                    product_no_snapshot=product.product_no,
                    product_name_snapshot=product.name,
                    supplier_name_snapshot=supplier.name,
                    quantity=current_quantity,
                    unit_cost=catalog.unit_cost,
                    subtotal=catalog.unit_cost * current_quantity,
                    production_date=now.date(),
                    expiration_date=now.date() + timedelta(days=catalog.shelf_life_days or 7),
                )
                db.add(latest_line)
                await db.flush()
                new_batch = InventoryBatch(
                    store_id=store.id,
                    batch_no="TMP-" + uuid4().hex[:20],
                    product_id=product.id,
                    purchase_item_id=latest_line.id,
                    production_date=now.date(),
                    expiration_date=latest_line.expiration_date,
                    initial_quantity=current_quantity,
                    remaining_quantity=current_quantity,
                    status=InventoryBatchStatus.AVAILABLE,
                    arrived_at=current_arrival,
                )
                db.add(new_batch)
                await db.flush()
                new_batch.batch_no = f"BAT{new_batch.id:08d}"
                product.stock_quantity = current_quantity + 8 * 2
            db.add(
                OperationAuditLog(
                    store_id=store.id,
                    employee_id=None,
                    module="demo_seed",
                    action="seed_store_business",
                    target_type="store",
                    target_id=store.id,
                    after_data={"products": len(chosen), "weeks": 8},
                    reason="日本门店面试演示数据",
                )
            )
            print(f"{store.store_no} {store.name}: {len(chosen)} 件商品、8 周销售样本")
        headquarters = await db.scalar(select(Employee).where(Employee.employee_no == "HQ00001"))
        notices = [
            (
                "全店安全衛生チェック",
                "各店舗の作業場・冷蔵設備・避難経路を確認してください。",
                [],
                None,
            ),
            (
                "首都圏店舗の棚卸し予定",
                "首都圏店舗は週末までに棚卸し予定を確認してください。",
                [12, 13, 14, 15, 16, 17, 18],
                None,
            ),
            (
                "青果部の品質管理",
                "青果部の担当者は入荷商品の品質を点検してください。",
                [],
                department_ids[0],
            ),
        ]
        recipients = (
            await db.scalars(
                select(Employee).where(
                    Employee.is_active.is_(True), Employee.role != EmployeeRole.HEADQUARTERS
                )
            )
        ).all()
        for title, content, target_stores, department_id in notices:
            if await db.scalar(
                select(ContactNotice.id)
                .where(ContactNotice.source == "headquarters", ContactNotice.title == title)
                .limit(1)
            ):
                continue
            notice = ContactNotice(
                store_id=None,
                source="headquarters",
                target_store_ids=target_stores,
                publisher_id=headquarters.id,
                title=title,
                content=content,
                priority="important",
                target_type="department" if department_id else "all",
                department_id=department_id,
                starts_at=now,
                deadline_at=now + timedelta(days=7),
                close_on_all_confirmed=True,
                status="published",
                version=1,
            )
            db.add(notice)
            await db.flush()
            for recipient in recipients:
                if target_stores and recipient.store_id not in target_stores:
                    continue
                if department_id and recipient.department_id != department_id:
                    continue
                db.add(
                    ContactNoticeRecipient(
                        notice_id=notice.id, employee_id=recipient.id, store_id=recipient.store_id
                    )
                )
            db.add(
                OperationAuditLog(
                    store_id=None,
                    employee_id=headquarters.id,
                    module="contact_notices",
                    action="demo_seed",
                    target_type="contact_notice",
                    target_id=notice.id,
                    after_data={"title": title},
                    reason="总部演示联络事项",
                )
            )
        await db.commit()
        print(f"完成：新增 {created_stores} 家门店、{created_staff} 名门店员工")
        if hq_password:
            print(f"总部账号 HQ00001 的一次性密码：{hq_password}")
        if created_staff:
            print(f"新建门店员工的一次性演示密码：{staff_password}")


async def main():
    try:
        await seed()
    finally:
        await async_engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
