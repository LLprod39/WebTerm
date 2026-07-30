import asyncio
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest
from channels.layers import get_channel_layer
from django.contrib.auth.models import User
from django.core.cache import cache
from django.db import close_old_connections, connection

from servers.agents.agent_dispatch import claim_next_agent_dispatch, enqueue_agent_run_dispatch
from servers.models import AgentRun, PlaybookRun, ServerAgent
from servers.playbooks.dispatch import claim_next_playbook_dispatch, enqueue_playbook_run_dispatch

pytestmark = pytest.mark.skipif(
    os.getenv("WEBTERM_REQUIRE_EXTERNAL_TEST_SERVICES") != "1",
    reason="requires the explicit PostgreSQL/Redis CI integration lane",
)


@pytest.mark.django_db
def test_ci_database_is_postgresql():
    assert connection.vendor == "postgresql"
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1")
        assert cursor.fetchone() == (1,)


@pytest.mark.django_db
def test_ci_redis_cache_roundtrip():
    cache.set("webterm:ci:cache", {"state": "ok"}, timeout=30)
    assert cache.get("webterm:ci:cache") == {"state": "ok"}
    cache.delete("webterm:ci:cache")


@pytest.mark.django_db
def test_ci_redis_channel_layer_roundtrip():
    async def scenario():
        layer = get_channel_layer()
        assert layer is not None
        channel = await layer.new_channel("webterm.ci.")
        await layer.send(channel, {"type": "ci.message", "state": "ok"})
        message = await asyncio.wait_for(layer.receive(channel), timeout=5)
        assert message == {"type": "ci.message", "state": "ok"}

    asyncio.run(scenario())


@pytest.mark.django_db(transaction=True)
def test_agent_dispatch_claims_four_rows_without_head_of_line_blocking(monkeypatch):
    user = User.objects.create_user(username="postgres-agent-claims", password="x")
    agent = ServerAgent.objects.create(
        user=user,
        name="Postgres claim probe",
        mode=ServerAgent.MODE_MINI,
        agent_type=ServerAgent.TYPE_CUSTOM,
    )
    for _index in range(4):
        run = AgentRun.objects.create(agent=agent, user=user, status=AgentRun.STATUS_PENDING)
        enqueue_agent_run_dispatch(
            run=run,
            agent_id=agent.id,
            user_id=user.id,
            server_ids=[],
            plan_only=False,
        )

    barrier = threading.Barrier(4)

    def slow_record_event(*_args, **_kwargs):
        time.sleep(0.25)

    monkeypatch.setattr("servers.agents.agent_dispatch.record_run_event", slow_record_event)
    monkeypatch.setattr("servers.agents.agent_dispatch._refresh_run_report_payload", lambda *_args: None)

    def claim(index: int) -> int:
        close_old_connections()
        try:
            barrier.wait(timeout=5)
            dispatch = claim_next_agent_dispatch(worker_name=f"postgres-agent-{index}")
            assert dispatch is not None
            return dispatch.id
        finally:
            close_old_connections()

    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=4) as pool:
        claimed_ids = list(pool.map(claim, range(4)))
    elapsed = time.perf_counter() - started

    assert len(set(claimed_ids)) == 4
    assert elapsed < 0.75, f"four skip-locked claims took {elapsed:.3f}s; expected near one 0.25s claim"


@pytest.mark.django_db(transaction=True)
def test_playbook_dispatch_validates_four_skip_locked_candidates_concurrently(monkeypatch):
    user = User.objects.create_user(username="postgres-playbook-claims", password="x")
    for index in range(4):
        run = PlaybookRun.objects.create(
            user=user,
            playbook_snapshot={"name": f"claim-{index}", "source_yaml": "- hosts: all\n  tasks: []\n"},
            target_server_ids=[],
            options={"engine": "ansible"},
        )
        enqueue_playbook_run_dispatch(run=run)

    barrier = threading.Barrier(4)

    def slow_authorization(_run):
        time.sleep(0.25)
        return True

    monkeypatch.setattr("servers.playbooks.dispatch._targets_still_authorized", slow_authorization)
    monkeypatch.setattr("servers.playbooks.dispatch.recover_expired_playbook_dispatches", lambda **_kwargs: {})

    def claim(index: int) -> int:
        close_old_connections()
        try:
            barrier.wait(timeout=5)
            dispatch = claim_next_playbook_dispatch(
                worker_name=f"postgres-playbook-{index}",
                global_concurrency=4,
                per_user_concurrency=4,
            )
            assert dispatch is not None
            return dispatch.id
        finally:
            close_old_connections()

    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=4) as pool:
        claimed_ids = list(pool.map(claim, range(4)))
    elapsed = time.perf_counter() - started

    assert len(set(claimed_ids)) == 4
    assert elapsed < 0.75, f"four skip-locked claims took {elapsed:.3f}s; expected near one 0.25s claim"


@pytest.mark.django_db(transaction=True)
def test_playbook_concurrent_claims_preserve_the_global_capacity_limit(monkeypatch):
    user = User.objects.create_user(username="postgres-playbook-capacity", password="x")
    for index in range(4):
        run = PlaybookRun.objects.create(
            user=user,
            playbook_snapshot={"name": f"capacity-{index}", "source_yaml": "- hosts: all\n  tasks: []\n"},
            target_server_ids=[],
            options={"engine": "ansible"},
        )
        enqueue_playbook_run_dispatch(run=run)

    barrier = threading.Barrier(4)
    monkeypatch.setattr("servers.playbooks.dispatch.recover_expired_playbook_dispatches", lambda **_kwargs: {})

    def claim(index: int) -> int | None:
        close_old_connections()
        try:
            barrier.wait(timeout=5)
            dispatch = claim_next_playbook_dispatch(
                worker_name=f"postgres-capacity-{index}",
                global_concurrency=2,
                per_user_concurrency=2,
            )
            return dispatch.id if dispatch is not None else None
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=4) as pool:
        claimed_ids = list(pool.map(claim, range(4)))

    assert len({dispatch_id for dispatch_id in claimed_ids if dispatch_id is not None}) == 2
