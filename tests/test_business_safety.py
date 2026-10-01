"""部署前的业务时间、AI 密钥加密和事务边界回归测试。"""

from datetime import datetime
from unittest.mock import AsyncMock, patch
from zoneinfo import ZoneInfo

import pytest
from cryptography.fernet import Fernet
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import purchase_scheduler
from app.core.business_time import business_now
from app.core.database import MarketFlowSession
from app.core.purchase_scheduler import _run_auto_receive_once
from app.services.ai_credentials import _cipher


def test_business_now_uses_japan_time() -> None:
    """业务时间不随云服务器的系统时区改变。"""

    now = business_now()
    assert now.tzinfo is None  # 现有 MySQL DATETIME 按日本本地时间保存。
    japan_now = datetime.now(ZoneInfo("Asia/Tokyo")).replace(tzinfo=None)
    assert abs((now - japan_now).total_seconds()) < 2


@pytest.mark.asyncio
async def test_receipt_catchup_does_not_run_todays_orders_before_noon(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """上午重启只补昨天及更早漏签收的订单。"""

    db = AsyncMock()

    class SessionContext:
        async def __aenter__(self) -> AsyncMock:
            return db

        async def __aexit__(self, *_args: object) -> None:
            return None

    receive = AsyncMock(return_value=[])
    monkeypatch.setattr(purchase_scheduler, "business_now", lambda: datetime(2026, 10, 1, 9))
    monkeypatch.setattr(purchase_scheduler, "async_session_factory", SessionContext)
    monkeypatch.setattr(purchase_scheduler, "auto_receive_due_purchases", receive)

    assert await _run_auto_receive_once() == 0
    assert receive.await_args.kwargs["arrived_at"] == datetime(2026, 9, 30, 12)


@pytest.mark.asyncio
async def test_deferred_session_commit_only_flushes() -> None:
    """AI 确认期间，现有 Service 的提交不会提前结束事务。"""

    session = MarketFlowSession()
    session.info["defer_commit"] = True
    session.flush = AsyncMock()  # type: ignore[method-assign]
    with patch.object(AsyncSession, "commit", new_callable=AsyncMock) as actual_commit:
        await session.commit()
        session.flush.assert_awaited_once()
        actual_commit.assert_not_awaited()
        session.info.pop("defer_commit")
        await session.commit()
        actual_commit.assert_awaited_once()
    await session.close()


def test_ai_credential_cipher_roundtrip(monkeypatch: pytest.MonkeyPatch) -> None:
    """数据库保存的是密文，加密主密钥留在服务端配置中。"""

    from app.core.config import settings

    monkeypatch.setattr(settings, "ai_key_encryption_key", Fernet.generate_key().decode())
    encrypted = _cipher().encrypt(b"secret-api-key")
    assert b"secret-api-key" not in encrypted
    assert _cipher().decrypt(encrypted) == b"secret-api-key"
