"""每分钟关闭到期联络事项，启动时补处理停机期间到期的数据。"""

import asyncio
import logging

from app.core.database import async_session_factory
from app.core.distributed_lock import distributed_lock
from app.services.contact_notices import refresh_expired_notices


# region 联络事项截止任务
async def run_contact_notice_scheduler(stop_event: asyncio.Event):
    while not stop_event.is_set():
        try:
            async with distributed_lock("contact-notices-close", ttl_seconds=120) as acquired:
                if acquired:
                    async with async_session_factory() as db:
                        await refresh_expired_notices(db)
        except Exception:
            logging.getLogger(__name__).exception("联络事项自动关闭失败")
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=60)
        except TimeoutError:
            pass


# endregion
