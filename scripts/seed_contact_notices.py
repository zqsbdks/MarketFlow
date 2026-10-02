"""生成日语联络事项演示数据；只新增，重复执行跳过同标题事项。"""

# ruff: noqa: E402

import asyncio
import sys
from datetime import timedelta
from io import TextIOWrapper
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
if isinstance(sys.stdout, TextIOWrapper):
    sys.stdout.reconfigure(encoding="utf-8")

from sqlalchemy import select

from app.core.business_time import business_now
from app.core.database import async_engine, async_session_factory
from app.crud.operation_audit_logs import create_operation_audit_log
from app.models.contact_notice import ContactNotice, ContactNoticeRecipient
from app.models.department import Department
from app.models.employee import Employee
from app.models.enums import EmployeeRole

# region 日语事项模板
TEMPLATES = [
    (
        "衛生管理チェックのお願い",
        "手洗い・消毒と作業台の清掃を実施してください。内容を確認したら確認ボタンを押してください。",
        "normal",
        "published",
        "mixed",
    ),
    (
        "冷蔵設備の温度確認",
        "冷蔵庫と冷凍庫の温度を確認し、異常がある場合は店長へ報告してください。",
        "urgent",
        "published",
        "pending",
    ),
    (
        "棚卸し手順の確認",
        "棚卸しは商品番号とロット番号を照合して実施してください。期限内に確認できなかった方は、内容を確認して補完してください。",
        "important",
        "closed",
        "expired",
    ),
    (
        "新しい値札の運用について",
        "割引商品の値札は通常価格と割引後価格を併記してください。全員の確認が完了したため、この連絡は終了しています。",
        "normal",
        "closed",
        "confirmed",
    ),
    (
        "来週の売場準備",
        "来週の売場変更についての下書きです。公開前に担当者と作業内容を確認します。",
        "normal",
        "draft",
        "pending",
    ),
    (
        "作業予定の変更のお知らせ",
        "作業予定を見直すため、この連絡は取り下げました。新しい予定は別途連絡します。",
        "important",
        "withdrawn",
        "pending",
    ),
]
# endregion


# region 安全追加と确认状态模拟
async def seed():
    now = business_now().replace(microsecond=0)
    async with async_session_factory() as db:
        employees = (
            await db.scalars(
                select(Employee).where(Employee.is_active.is_(True)).order_by(Employee.id)
            )
        ).all()
        manager = None
        for employee in employees:
            if employee.role == EmployeeRole.STORE_MANAGER:
                manager = employee
                break
        if manager is None:
            raise RuntimeError("没有启用的店长账号，无法生成联络事项")
        departments = (
            await db.scalars(
                select(Department).where(Department.is_active.is_(True)).order_by(Department.id)
            )
        ).all()
        groups = [("all", None, "全員", employees)]
        personal = [manager]
        for department in departments:
            members = []
            for employee in employees:
                if employee.department_id == department.id:
                    members.append(employee)
            if members:
                groups.append(("department", department.id, department.name, members))
                personal.append(members[0])
        groups.append(("personal", None, "担当者", personal))
        created = 0
        skipped = 0
        for target_type, department_id, label, recipients in groups:
            for index, (title, content, priority, status, mode) in enumerate(TEMPLATES):
                full_title = f"【デモ・{label}】{title}"
                existing = await db.scalar(
                    select(ContactNotice.id).where(ContactNotice.title == full_title)
                )
                if existing is not None:
                    skipped += 1
                    continue
                deadline = now + timedelta(days=2, hours=index)
                closed_at = None
                close_reason = None
                if mode == "expired":
                    deadline = now - timedelta(hours=4)
                    closed_at = deadline
                    close_reason = "deadline"
                elif mode == "confirmed":
                    closed_at = now - timedelta(hours=2)
                    close_reason = "all_confirmed"
                elif status == "withdrawn":
                    closed_at = now - timedelta(hours=1)
                    close_reason = "withdrawn"
                notice = ContactNotice(
                    title=full_title,
                    content=content,
                    priority=priority,
                    target_type=target_type,
                    department_id=department_id,
                    publisher_id=manager.id,
                    starts_at=now - timedelta(days=2),
                    deadline_at=deadline,
                    close_on_all_confirmed=True,
                    status=status,
                    closed_at=closed_at,
                    close_reason=close_reason,
                    version=1,
                    created_at=now - timedelta(days=2, minutes=index),
                )
                db.add(notice)
                await db.flush()
                for position, employee in enumerate(recipients):
                    confirmed_at = None
                    read_at = None
                    if mode == "confirmed" or (mode in ("mixed", "expired") and position % 3 == 1):
                        read_at = now - timedelta(days=1, hours=1)
                        confirmed_at = now - timedelta(days=1)
                    elif mode == "mixed" and position % 3 == 2:
                        read_at = now - timedelta(hours=3)
                    db.add(
                        ContactNoticeRecipient(
                            notice_id=notice.id,
                            employee_id=employee.id,
                            read_at=read_at,
                            confirmed_at=confirmed_at,
                        )
                    )
                # 演示确认时间在审计中明确标注，不伪装成员工的真实操作。
                await create_operation_audit_log(
                    employee_id=None,
                    module="contact_notices",
                    action="demo_seed",
                    target_type="contact_notice",
                    target_id=notice.id,
                    before_data=None,
                    after_data={
                        "title": notice.title,
                        "status": status,
                        "target_type": target_type,
                        "recipient_count": len(recipients),
                    },
                    reason="日本語デモデータ：確認履歴はシミュレーションです",
                    db=db,
                )
                created += 1
        await db.commit()
        print(f"新增 {created} 条日语联络事项，跳过 {skipped} 条已有事项；发布者：{manager.name}")
        print("范围：全体、每个启用部门、个人；状态：已发布、期限关闭、全员确认关闭、草稿、已撤回")


async def main():
    try:
        await seed()
    finally:
        await async_engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
# endregion
