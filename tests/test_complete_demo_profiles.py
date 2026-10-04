"""Profile completion preserves existing information and is safe to repeat."""

from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select

from app.models.employee import Employee
from app.models.employee_detail import EmployeeDetail
from app.models.enums import EmployeeGender, EmploymentStatus
from scripts import complete_demo_employee_profiles as script


@pytest.mark.asyncio
async def test_complete_preserves_existing_and_is_idempotent(store_database, monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(script, "async_session_factory", store_database)
    monkeypatch.setattr(script, "async_engine", SimpleNamespace(dispose=AsyncMock()))
    async with store_database() as db:
        db.add(
            EmployeeDetail(
                employee_id=1,
                gender=EmployeeGender.FEMALE,
                birth_date=date(1980, 1, 1),
                hire_date=date(2020, 1, 1),
                phone="existing-phone",
                address=None,
                employment_status=EmploymentStatus.ON_LEAVE,
            )
        )
        await db.commit()
    await script.main()
    async with store_database() as db:
        profiles = list((await db.scalars(select(EmployeeDetail))).all())
        assert len(profiles) == 5
        assert all(not script.missing_fields(d) for d in profiles)
        original = await db.get(EmployeeDetail, 1)
        assert original.phone == "existing-phone" and original.gender == EmployeeGender.FEMALE
        assert original.employment_status == EmploymentStatus.ON_LEAVE
        assert original.birth_date == date(1980, 1, 1)
        assert (await db.get(Employee, 1)).password_hash == "test-only"
        snapshots = [d.address for d in profiles]
    await script.main()
    async with store_database() as db:
        assert [d.address for d in (await db.scalars(select(EmployeeDetail))).all()] == snapshots
    assert len(list((tmp_path / ".cache").glob("*.json"))) == 1
