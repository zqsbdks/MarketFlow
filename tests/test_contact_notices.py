"""联络事项权限、自动关闭、幂等确认和名单隐私测试。"""

from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.contact_notice import ContactNotice, ContactNoticeRecipient
from app.models.employee import Employee
from app.models.enums import EmployeeRole
from app.schemas.contact_notices_requests import ContactNoticeWriteRequest
from app.services import contact_notices as service

NOW = datetime(2026, 10, 1, 12)


def employee(role=EmployeeRole.CONTRACT_WORKER):
    return Employee(
        id=2,
        store_id=1,
        name="田中",
        employee_no="E00002",
        department_id=1,
        role=role,
        is_active=True,
        must_change_password=False,
    )


def notice(**changes):
    values = dict(
        id=1,
        store_id=1,
        title="冷蔵庫点検",
        content="温度を確認してください",
        priority="normal",
        target_type="department",
        department_id=1,
        publisher_id=3,
        starts_at=NOW - timedelta(hours=1),
        deadline_at=NOW + timedelta(hours=1),
        close_on_all_confirmed=True,
        status="published",
        version=1,
        closed_at=None,
        close_reason=None,
        created_at=NOW,
        updated_at=NOW,
    )
    values.update(changes)
    return ContactNotice(**values)


@pytest.fixture
def setup(monkeypatch):
    monkeypatch.setattr(service, "business_now", lambda: NOW)
    monkeypatch.setattr(service, "audit", AsyncMock())
    return AsyncMock(spec=AsyncSession)


@pytest.mark.asyncio
async def test_contract_worker_cannot_publish_to_everyone(setup):
    request = ContactNoticeWriteRequest(title="確認", content="確認", target_type="all")
    with pytest.raises(HTTPException) as error:
        await service.resolve_recipients(request, employee(), setup)
    assert error.value.status_code == 403


@pytest.mark.asyncio
async def test_contract_worker_can_publish_to_own_department(setup):
    setup.get.return_value = SimpleNamespace(is_active=True)
    setup.scalars.return_value = SimpleNamespace(all=lambda: [employee()])
    request = ContactNoticeWriteRequest(
        title="確認", content="確認", target_type="department", department_id=1
    )
    recipients, department_id, _ = await service.resolve_recipients(request, employee(), setup)
    assert len(recipients) == 1 and department_id == 1


@pytest.mark.asyncio
async def test_cross_department_recipient_is_rejected(setup):
    other = employee()
    other.department_id = 2
    setup.scalars.return_value = SimpleNamespace(all=lambda: [other])
    request = ContactNoticeWriteRequest(
        title="確認", content="確認", target_type="personal", employee_ids=[2]
    )
    with pytest.raises(HTTPException) as error:
        await service.resolve_recipients(request, employee(), setup)
    assert error.value.status_code == 403


@pytest.mark.asyncio
async def test_contract_worker_can_send_to_specific_colleague_in_own_department(setup):
    colleague = employee()
    colleague.id = 3
    setup.scalars.return_value = SimpleNamespace(all=lambda: [colleague])
    request = ContactNoticeWriteRequest(
        title="確認", content="確認", target_type="personal", employee_ids=[3]
    )
    recipients, department_id, _ = await service.resolve_recipients(request, employee(), setup)
    assert [item.id for item in recipients] == [3]
    assert department_id == 1


@pytest.mark.asyncio
async def test_contract_worker_cannot_send_to_colleague_in_another_store(setup):
    colleague = employee()
    colleague.id = 3
    colleague.store_id = 2
    setup.scalars.return_value = SimpleNamespace(all=lambda: [colleague])
    request = ContactNoticeWriteRequest(
        title="確認", content="確認", target_type="personal", employee_ids=[3]
    )
    with pytest.raises(HTTPException) as error:
        await service.resolve_recipients(request, employee(), setup)
    assert error.value.status_code == 403


@pytest.mark.asyncio
async def test_expired_deadline_closes_and_preserves_notice(setup):
    item = notice(deadline_at=NOW)
    await service.close_if_due(item, setup)
    assert item.status == "closed" and item.close_reason == "deadline" and item.version == 2
    setup.delete.assert_not_called()
    service.audit.assert_awaited_once()


@pytest.mark.asyncio
async def test_all_confirmed_closes_notice(setup):
    setup.scalar.side_effect = [3, 0]
    item = notice()
    await service.close_if_due(item, setup)
    assert item.status == "closed" and item.close_reason == "all_confirmed"


@pytest.mark.asyncio
async def test_pending_recipient_keeps_notice_open(setup):
    setup.scalar.side_effect = [3, 1]
    item = notice()
    await service.close_if_due(item, setup)
    assert item.status == "published"


def test_stale_version_rejected():
    with pytest.raises(HTTPException) as error:
        service.check_version(notice(version=2), 1)
    assert error.value.status_code == 409


@pytest.mark.asyncio
async def test_normal_recipient_cannot_see_employee_confirmation_list(setup, monkeypatch):
    record = ContactNoticeRecipient(employee_id=2, store_id=1, read_at=None, confirmed_at=None)
    monkeypatch.setattr(
        service, "get_recipients", AsyncMock(return_value=[(record, "田中", "青果部")])
    )
    setup.get.side_effect = [employee(), SimpleNamespace(name="青果部")]
    response = await service.build_response(notice(), employee(), setup, detail=True)
    assert response.recipients == [] and response.employee_ids == [] and response.can_confirm


@pytest.mark.asyncio
async def test_manager_sees_three_lights_without_read_pending_status(setup, monkeypatch):
    records = []
    for employee_id, confirmed_at in [(2, NOW), (3, None)]:
        records.append(
            (
                ContactNoticeRecipient(
                    employee_id=employee_id, store_id=1, read_at=NOW, confirmed_at=confirmed_at
                ),
                "田中",
                "青果部",
            )
        )
    monkeypatch.setattr(service, "get_recipients", AsyncMock(return_value=records))
    setup.get.side_effect = [employee(), SimpleNamespace(name="青果部")]
    response = await service.build_response(
        notice(deadline_at=NOW), employee(EmployeeRole.STORE_MANAGER), setup, detail=True
    )
    assert [item.light for item in response.recipients] == ["green", "red"]


@pytest.mark.asyncio
async def test_repeat_confirmation_is_idempotent(setup, monkeypatch):
    item = notice(status="closed")
    record = ContactNoticeRecipient(employee_id=2, store_id=1, read_at=NOW, confirmed_at=NOW)
    monkeypatch.setattr(service, "current_employee", AsyncMock(return_value=employee()))
    monkeypatch.setattr(service, "get_notice", AsyncMock(return_value=item))
    monkeypatch.setattr(service, "build_response", AsyncMock(return_value="ok"))
    setup.scalar.return_value = record
    assert await service.action_notice(1, "confirm", None, 2, setup) == "ok"
    service.audit.assert_not_awaited()
    assert record.confirmed_at == NOW


@pytest.mark.asyncio
async def test_non_recipient_cannot_open_notice(setup, monkeypatch):
    monkeypatch.setattr(service, "current_employee", AsyncMock(return_value=employee()))
    monkeypatch.setattr(service, "get_notice", AsyncMock(return_value=notice()))
    setup.scalar.return_value = None
    with pytest.raises(HTTPException) as error:
        await service.detail_notice(1, 2, setup)
    assert error.value.status_code == 403
