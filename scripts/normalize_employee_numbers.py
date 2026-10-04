"""Normalize employee login numbers to E + five-digit primary key.

Run with python -m scripts.normalize_employee_numbers.
Save a mapping before changing anything; preserve passwords and identities.
"""

import asyncio
import json
from pathlib import Path
from uuid import uuid4

from sqlalchemy import select

from app.core.database import async_engine, async_session_factory
from app.models.employee import Employee


async def main():
    try:
        async with async_session_factory() as db:
            employees = list(
                (await db.scalars(select(Employee).order_by(Employee.id).with_for_update())).all()
            )
            changes = [e for e in employees if e.employee_no != f"E{e.id:05d}"]
            mapping = [{"id": e.id, "old": e.employee_no, "new": f"E{e.id:05d}"} for e in changes]
            if changes:
                backup = Path(".cache") / f"employee-number-map-{uuid4().hex}.json"
                backup.parent.mkdir(exist_ok=True)
                backup.write_text(
                    json.dumps(mapping, ensure_ascii=False, indent=2), encoding="utf-8"
                )
                # Move all changed numbers aside before assigning final numbers.
                for employee in changes:
                    employee.employee_no = f"TMP-{uuid4().hex[:16]}"
                await db.flush()
                for employee in changes:
                    employee.employee_no = f"E{employee.id:05d}"
                await db.flush()
                if any(e.employee_no != f"E{e.id:05d}" for e in employees):
                    raise RuntimeError("Employee number validation failed")
                await db.commit()
                print(f"Mapping saved: {backup}")
            print(f"Employees: {len(employees)}; updated: {len(changes)}")
            for employee in employees:
                if employee.store_id is None:
                    print(f"Headquarters: id={employee.id}, number={employee.employee_no}")
    finally:
        await async_engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
