from __future__ import annotations

import asyncio
from collections import deque
from types import SimpleNamespace

import pytest
from django.core.management.base import CommandError

from servers.management.commands.run_agent_execution_plane import Command


def test_agent_execution_worker_uses_multiple_local_slots(monkeypatch):
    dispatches = deque([SimpleNamespace(id=101), SimpleNamespace(id=102)])
    active = 0
    maximum_active = 0
    both_started = asyncio.Event()

    monkeypatch.setattr(
        "servers.management.commands.run_agent_execution_plane.cleanup_stale_agent_runs",
        lambda: 0,
    )
    monkeypatch.setattr(
        "servers.management.commands.run_agent_execution_plane.heartbeat_background_worker",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        "servers.management.commands.run_agent_execution_plane.claim_next_agent_dispatch",
        lambda **_kwargs: dispatches.popleft() if dispatches else None,
    )

    async def fake_execute(_dispatch_id: int, *, worker_key: str, lease_seconds: int) -> bool:
        nonlocal active, maximum_active
        _ = (worker_key, lease_seconds)
        active += 1
        maximum_active = max(maximum_active, active)
        if active == 2:
            both_started.set()
        await asyncio.wait_for(both_started.wait(), timeout=0.5)
        await asyncio.sleep(0.01)
        active -= 1
        return True

    monkeypatch.setattr(Command, "_execute_dispatch", staticmethod(fake_execute))

    async def scenario() -> None:
        command = Command()
        with pytest.raises(TimeoutError):
            await asyncio.wait_for(
                command._run_loop(
                    worker_key="parallel-test",
                    lease_seconds=180,
                    interval=0.01,
                    global_concurrency=2,
                    per_user_concurrency=2,
                    worker_concurrency=2,
                ),
                timeout=0.15,
            )

    asyncio.run(scenario())
    assert maximum_active == 2


def test_restricted_pilot_refuses_global_agent_concurrency_above_ten(monkeypatch):
    monkeypatch.setenv("PILOT_RESTRICTED_MODE", "true")

    with pytest.raises(CommandError, match="global concurrency to 10"):
        Command().handle(
            interval=5,
            lease_seconds=180,
            limit=1,
            worker_key="pilot-limit-test",
            global_concurrency=11,
            per_user_concurrency=2,
            worker_concurrency=1,
            once=True,
        )
