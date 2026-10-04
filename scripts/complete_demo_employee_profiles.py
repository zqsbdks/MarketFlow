"""补齐模拟员工资料；仅填缺失项，保留现有身份、密码和雇佣信息。

生成的电话和地址均为演示用途。Run: python -m scripts.complete_demo_employee_profiles
"""

import asyncio
import calendar
import json
import random
from datetime import date
from pathlib import Path
from uuid import uuid4

from sqlalchemy import select

from app.core.business_time import business_now
from app.core.database import async_engine, async_session_factory
from app.models.employee import Employee
from app.models.employee_detail import EmployeeDetail
from app.models.enums import EmployeeGender, EmploymentStatus


def missing_fields(detail):
    if detail is None:
        return ["gender", "birth_date", "hire_date", "phone", "address", "employment_status"]
    return [
        field
        for field in ("gender", "birth_date", "hire_date", "phone", "address", "employment_status")
        if not getattr(detail, field)
        or (field == "gender" and detail.gender == EmployeeGender.UNSPECIFIED)
    ]


async def main():
    try:
        async with async_session_factory() as db:
            employees = list(
                (await db.scalars(select(Employee).order_by(Employee.id).with_for_update())).all()
            )
            details = {
                d.employee_id: d
                for d in (await db.scalars(select(EmployeeDetail).with_for_update())).all()
            }
            backup = []
            today = business_now().date()
            for employee in employees:
                detail = details.get(employee.id)
                missing = missing_fields(detail)
                if not missing:
                    continue
                backup.append(
                    {
                        "employee_id": employee.id,
                        "missing_fields": missing,
                        "before": {
                            field: str(getattr(detail, field))
                            if getattr(detail, field) is not None
                            else None
                            for field in missing
                        }
                        if detail
                        else None,
                    }
                )
                rng = random.Random(20261004 + employee.id)
                if detail is None:
                    detail = EmployeeDetail(
                        employee_id=employee.id,
                        hire_date=today,
                        employment_status=EmploymentStatus.EMPLOYED,
                    )
                    db.add(detail)
                if "hire_date" in missing:
                    detail.hire_date = today
                if "gender" in missing:
                    detail.gender = rng.choice([EmployeeGender.MALE, EmployeeGender.FEMALE])
                if "birth_date" in missing:
                    year = detail.hire_date.year - rng.randint(20, 55)
                    month = rng.randint(1, 12)
                    detail.birth_date = date(
                        year, month, rng.randint(1, calendar.monthrange(year, month)[1])
                    )
                if "phone" in missing:
                    detail.phone = f"090-0000-{employee.id:04d}"
                if "address" in missing:
                    detail.address = (
                        f"デモ住所（架空）・店舗{employee.store_id or 0:04d}・{employee.id}号"
                    )
                if "employment_status" in missing:
                    detail.employment_status = EmploymentStatus.EMPLOYED
            if backup:
                path = Path(".cache") / f"employee-profile-backup-{uuid4().hex}.json"
                path.parent.mkdir(exist_ok=True)
                path.write_text(json.dumps(backup, ensure_ascii=False, indent=2), encoding="utf-8")
                await db.commit()
                print(f"Backup: {path}")
            print(f"Employees: {len(employees)}; completed: {len(backup)}")
    finally:
        await async_engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
