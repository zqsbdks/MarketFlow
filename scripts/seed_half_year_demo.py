"""追加半年日语演示业务，保留现有账号和数据；重复执行不会重复导入。"""

import asyncio
import calendar
import random
from datetime import datetime, time, timedelta

from sqlalchemy import func, select

from app.core.business_time import business_now
from app.core.database import async_engine, async_session_factory
from app.core.security import hash_password
from app.models.contact_notice import ContactNotice, ContactNoticeRecipient
from app.models.department import Department
from app.models.discount_rule import DiscountRule
from app.models.employee import Employee
from app.models.employee_detail import EmployeeDetail
from app.models.enums import EmployeeRole
from app.models.inventory_batch import InventoryBatch
from app.models.operation_audit_log import OperationAuditLog
from app.models.product import Product
from app.models.supplier import Supplier
from scripts.seed_contact_notices import TEMPLATES
from scripts.seed_japanese_demo import (
    batch_status,
    create_audit_logs,
    create_purchases_and_batches,
    create_sales,
)

MARKER = "half_year_japanese_v1"


async def seed():
    now = business_now().replace(microsecond=0)
    month_index = now.year * 12 + now.month - 1 - 6
    year, month = divmod(month_index, 12)
    month += 1
    start = now.date().replace(
        year=year, month=month, day=min(now.day, calendar.monthrange(year, month)[1])
    )
    async with async_session_factory() as db:
        if await db.scalar(
            select(OperationAuditLog.id).where(OperationAuditLog.action == MARKER).limit(1)
        ):
            print("Half-year demo already imported; no duplicate data added.")
            return
        manager = await db.scalar(
            select(Employee)
            .where(Employee.role == EmployeeRole.STORE_MANAGER)
            .order_by(Employee.id)
        )
        if manager is None or manager.store_id != 1:
            raise RuntimeError("This demo requires the existing DP0001 manager.")
        employees = list(
            (
                await db.scalars(
                    select(Employee)
                    .where(Employee.store_id == manager.store_id)
                    .order_by(Employee.id)
                )
            ).all()
        )
        departments = {d.code: d for d in (await db.scalars(select(Department))).all()}
        suppliers = list(
            (
                await db.scalars(
                    select(Supplier)
                    .where(Supplier.store_id == manager.store_id)
                    .order_by(Supplier.id)
                )
            ).all()
        )
        products = list(
            (
                await db.scalars(
                    select(Product).where(Product.store_id == manager.store_id).order_by(Product.id)
                )
            ).all()
        )
        rules = {}
        for key, name in {
            "PRODUCE": "青果朝市10％OFF",
            "MEAT": "週末お肉15％OFF",
            "SEAFOOD": "鮮魚夕市20％OFF",
            "DELI": "惣菜閉店前30％OFF",
        }.items():
            rule = await db.scalar(select(DiscountRule).where(DiscountRule.name == name))
            if rule is None and key == "PRODUCE":
                rule = await db.scalar(
                    select(DiscountRule)
                    .where(
                        DiscountRule.department_id == departments[key].id,
                        DiscountRule.is_active.is_(True),
                    )
                    .order_by(DiscountRule.id)
                )
            if rule is None:
                raise RuntimeError("Missing discount template: " + key)
            rules[key] = rule

        print(f"Generating purchases and inventory: {start} to {now.date()}", flush=True)
        rng = random.Random(20261004)
        purchases, ledgers = await create_purchases_and_batches(
            db,
            rng,
            start,
            now.date() + timedelta(days=2),
            departments,
            employees,
            suppliers,
            products,
            interval_days=1,
            number_prefix="H",
        )
        print(f"Purchases: {len(purchases)}. Generating sales...", flush=True)
        sales = await create_sales(
            db,
            rng,
            start,
            now.date(),
            departments,
            employees,
            products,
            ledgers,
            rules,
            volume_multiplier=3,
            number_prefix="H",
        )
        for ledger in ledgers:
            ledger.batch.status = batch_status(ledger.batch, ledger.product, now.date())
        await db.flush()
        for product in products:
            product.stock_quantity = int(
                await db.scalar(
                    select(func.sum(InventoryBatch.remaining_quantity)).where(
                        InventoryBatch.product_id == product.id
                    )
                )
                or 0
            )
        await create_audit_logs(db, manager, [], [], [], purchases, ledgers, sales, {})
        print(f"Sales: {len(sales)}. Generating notices...", flush=True)

        hq = await db.scalar(select(Employee).where(Employee.employee_no == "HQ00001"))
        if hq is None:
            hq = Employee(
                employee_no="HQ00001",
                name="本部管理者",
                role=EmployeeRole.HEADQUARTERS,
                password_hash=hash_password(random.SystemRandom().randbytes(24).hex()),
                must_change_password=True,
                store_id=None,
                department_id=None,
                detail=EmployeeDetail(hire_date=start),
            )
            db.add(hq)
            await db.flush()
        groups = [("all", None, "全員", employees)]
        for department in departments.values():
            members = [e for e in employees if e.department_id == department.id]
            if members:
                groups.append(("department", department.id, department.name, members))
        groups.append(("personal", None, "担当者", [manager, employees[-1]]))
        notice_count = 0
        for day_index in range((now.date() - start).days + 1):
            day = start + timedelta(days=day_index)
            for group_index, (target, department_id, label, recipients) in enumerate(groups):
                index = (day_index + group_index) % len(TEMPLATES)
                title, content, priority, _, _ = TEMPLATES[index]
                content = content.replace(
                    "全員の確認が完了したため、この連絡は終了しています。",
                    "値札の更新後は売場の表示とレジ登録価格を照合してください。",
                )
                if index == 1:
                    priority = "normal"
                created = datetime.combine(day, time(8, group_index * 5))
                if created > now:
                    created = now - timedelta(minutes=group_index + 1)
                deadline = created + timedelta(days=3)
                status = "closed" if deadline <= now else "published"
                if index == 4:
                    status = "draft"
                elif index == 5:
                    status = "withdrawn"
                confirmed_all = day_index % 4 == 0 and status == "closed"
                close_time = (
                    created + timedelta(hours=2)
                    if confirmed_all
                    else deadline
                    if status == "closed"
                    else created + timedelta(hours=1)
                    if status == "withdrawn"
                    else None
                )
                if close_time is not None and close_time > now:
                    close_time = now
                headquarters = target == "all" and day_index % 7 == 0
                notice = ContactNotice(
                    store_id=None if headquarters else manager.store_id,
                    source="headquarters" if headquarters else "store",
                    target_store_ids=[manager.store_id] if headquarters else None,
                    publisher_id=hq.id if headquarters else manager.id,
                    title=f"【{day:%m/%d}・{label}】{title}",
                    content=content + "\n半年分の運営シミュレーション記録です。",
                    priority=priority,
                    target_type=target,
                    department_id=department_id,
                    starts_at=created,
                    deadline_at=deadline,
                    status=status,
                    close_on_all_confirmed=True,
                    closed_at=close_time,
                    close_reason=("all_confirmed" if confirmed_all else "deadline")
                    if status == "closed"
                    else "withdrawn"
                    if status == "withdrawn"
                    else None,
                    created_at=created,
                    updated_at=close_time or created,
                )
                db.add(notice)
                await db.flush()
                if status != "draft":
                    for position, employee in enumerate(recipients):
                        read = created + timedelta(hours=1)
                        confirm = created + timedelta(hours=2)
                        db.add(
                            ContactNoticeRecipient(
                                notice_id=notice.id,
                                employee_id=employee.id,
                                store_id=employee.store_id,
                                created_at=created,
                                read_at=read
                                if read <= now and (confirmed_all or position % 3 != 0)
                                else None,
                                confirmed_at=confirm
                                if confirm <= now
                                and status != "withdrawn"
                                and (confirmed_all or position % 3 == 1)
                                else None,
                            )
                        )
                db.add(
                    OperationAuditLog(
                        store_id=manager.store_id,
                        employee_id=None,
                        module="contact_notices",
                        action="demo_seed",
                        target_type="contact_notice",
                        target_id=notice.id,
                        after_data={"title": notice.title, "status": status},
                        reason="日本語デモ：確認履歴はシミュレーションです",
                        created_at=created,
                    )
                )
                notice_count += 1
        db.add(
            OperationAuditLog(
                store_id=manager.store_id,
                employee_id=None,
                module="demo_seed",
                action=MARKER,
                target_type="store",
                target_id=manager.store_id,
                after_data={"start": str(start), "end": str(now.date())},
                reason="半年分の日本語デモデータを追加",
            )
        )
        await db.commit()
        print(
            f"COMMITTED: {len(purchases)} purchases, {len(sales)} sales, {notice_count} notices",
            flush=True,
        )
        for model in [Product, Employee, ContactNotice, ContactNoticeRecipient]:
            count = await db.scalar(select(func.count()).select_from(model))
            print(f"{model.__tablename__}: {count}")


async def main():
    try:
        await seed()
        from scripts.normalize_demo_data import normalize

        await normalize()
    finally:
        await async_engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
