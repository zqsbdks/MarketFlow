"""可选 MySQL 完整流程测试，所有测试变更最终回滚。"""

import os
from datetime import timedelta

import pytest
from sqlalchemy import select

from app.core.business_time import business_now
from app.core.database import async_engine, async_session_factory
from app.models.employee import Employee
from app.models.enums import EmployeeRole
from app.schemas.contact_notices_requests import (
    ContactNoticeActionRequest,
    ContactNoticeListRequest,
    ContactNoticeWriteRequest,
)
from app.services.contact_notices import action_notice, detail_notice, list_notices, save_notice


@pytest.mark.integration
@pytest.mark.asyncio
async def test_mysql_publish_confirm_close_and_repeat():
    if os.getenv("RUN_MYSQL_TESTS") != "1":
        pytest.skip("set RUN_MYSQL_TESTS=1 to run the transactional MySQL notice flow")
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
            request = ContactNoticeWriteRequest(
                title="動作確認（ロールバック）",
                content="確認後自動終了",
                target_type="personal",
                employee_ids=[manager.id],
                deadline_at=business_now() + timedelta(hours=1),
            )
            draft = await save_notice(request, manager.id, db)
            published = await action_notice(
                draft.id,
                "publish",
                ContactNoticeActionRequest(expected_version=draft.version),
                manager.id,
                db,
            )
            assert published.status == "published" and published.recipient_count == 1
            received = await list_notices(
                ContactNoticeListRequest(target_type="personal", confirmed=False), manager.id, db
            )
            assert any(item.id == draft.id for item in received.items)
            detail = await detail_notice(draft.id, manager.id, db)
            assert detail.read_at is not None and detail.recipients[0].light == "yellow"
            closed = await action_notice(draft.id, "confirm", None, manager.id, db)
            assert closed.status == "closed" and closed.close_reason == "all_confirmed"
            assert closed.recipients[0].light == "green"
            repeated = await action_notice(draft.id, "confirm", None, manager.id, db)
            assert repeated.confirmed_at == closed.confirmed_at
        finally:
            await db.rollback()
    # Each pytest-asyncio test owns a separate loop; pooled aiomysql connections
    # must not be reused by the next integration test's event loop.
    await async_engine.dispose()
