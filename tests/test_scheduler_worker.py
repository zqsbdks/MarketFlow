"""独立调度进程启动和停止两个调度器的回归测试。"""

import asyncio
from types import SimpleNamespace

from app.core import scheduler_worker


async def test_worker_runs_both_schedulers_before_cleanup(monkeypatch):
    events = []
    stop_events = []
    callbacks = []

    async def initialize():
        events.append("initialize")

    async def run_scheduler(name, stop_event):
        events.append(name)
        stop_events.append(stop_event)
        if len(stop_events) == 2:
            # 模拟进程收到停止信号，两个任务都应能结束。
            callbacks[0]()
        await stop_event.wait()
        events.append(f"{name}-stopped")

    async def purchases(stop_event):
        await run_scheduler("purchases", stop_event)

    async def notices(stop_event):
        await run_scheduler("notices", stop_event)

    async def close_redis():
        events.append("close-redis")

    async def dispose():
        events.append("dispose")

    loop = asyncio.get_running_loop()
    monkeypatch.setattr(
        loop, "add_signal_handler", lambda signum, callback: callbacks.append(callback)
    )
    monkeypatch.setattr(scheduler_worker, "initialize_business_cache", initialize)
    monkeypatch.setattr(scheduler_worker, "run_purchase_scheduler", purchases)
    monkeypatch.setattr(scheduler_worker, "run_contact_notice_scheduler", notices)
    monkeypatch.setattr(scheduler_worker, "close_redis", close_redis)
    monkeypatch.setattr(scheduler_worker, "async_engine", SimpleNamespace(dispose=dispose))

    await asyncio.wait_for(scheduler_worker.main(), timeout=1)

    assert stop_events[0] is stop_events[1]
    assert events[0] == "initialize"
    assert {"purchases-stopped", "notices-stopped"} <= set(events[:-2])
    assert events[-2:] == ["close-redis", "dispose"]
