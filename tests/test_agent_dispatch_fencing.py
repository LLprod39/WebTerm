from __future__ import annotations

from datetime import timedelta

import pytest
from django.contrib.auth.models import User
from django.utils import timezone

from servers.agent_dispatch import (
    claim_next_agent_dispatch,
    complete_agent_dispatch,
    enqueue_agent_run_dispatch,
    fail_agent_dispatch,
    heartbeat_agent_dispatch,
    serialize_agent_dispatch,
)
from servers.models import AgentRun, AgentRunDispatch, AgentRunEvent, ServerAgent


def _queued_dispatch(username: str) -> tuple[AgentRun, AgentRunDispatch]:
    user = User.objects.create_user(username=username, password="x")
    agent = ServerAgent.objects.create(
        user=user,
        name=f"Agent {username}",
        mode=ServerAgent.MODE_MINI,
        agent_type=ServerAgent.TYPE_CUSTOM,
    )
    run = AgentRun.objects.create(agent=agent, user=user, status=AgentRun.STATUS_PENDING)
    dispatch = enqueue_agent_run_dispatch(
        run=run,
        agent_id=agent.id,
        user_id=user.id,
        server_ids=[],
        plan_only=False,
    )
    return run, dispatch


@pytest.mark.django_db
def test_expired_agent_dispatch_stops_after_three_attempts():
    run, dispatch = _queued_dispatch("agent-attempt-limit")

    for attempt in range(1, 4):
        claimed = claim_next_agent_dispatch(worker_name=f"worker-{attempt}", lease_seconds=30)
        assert claimed is not None
        assert claimed.id == dispatch.id
        assert claimed.attempt_count == attempt
        AgentRunDispatch.objects.filter(pk=dispatch.id).update(
            lease_expires_at=timezone.now() - timedelta(seconds=1)
        )

    assert claim_next_agent_dispatch(worker_name="worker-4", lease_seconds=30) is None

    dispatch.refresh_from_db()
    run.refresh_from_db()
    assert dispatch.status == AgentRunDispatch.STATUS_FAILED
    assert dispatch.attempt_count == 3
    assert dispatch.max_attempts == 3
    assert "exhausted" in dispatch.error.lower()
    assert run.status == AgentRun.STATUS_FAILED
    assert AgentRunEvent.objects.filter(run=run, event_type="agent_dispatch_attempts_exhausted").count() == 1
    assert serialize_agent_dispatch(dispatch)["max_attempts"] == 3


@pytest.mark.django_db
def test_stale_agent_worker_cannot_heartbeat_complete_or_fail_reclaimed_attempt():
    run, dispatch = _queued_dispatch("agent-attempt-fence")
    first = claim_next_agent_dispatch(worker_name="worker-old", lease_seconds=30)
    assert first is not None
    first_attempt = first.attempt_count
    AgentRunDispatch.objects.filter(pk=dispatch.id).update(
        lease_expires_at=timezone.now() - timedelta(seconds=1)
    )
    second = claim_next_agent_dispatch(worker_name="worker-new", lease_seconds=30)
    assert second is not None
    second_attempt = second.attempt_count

    assert (
        heartbeat_agent_dispatch(
            dispatch.id,
            worker_name="worker-old",
            attempt_count=first_attempt,
            lease_seconds=30,
        )
        is False
    )
    assert (
        complete_agent_dispatch(
            dispatch.id,
            worker_name="worker-old",
            attempt_count=first_attempt,
            summary={"result": "stale"},
        )
        is None
    )
    assert (
        fail_agent_dispatch(
            dispatch.id,
            worker_name="worker-old",
            attempt_count=first_attempt,
            error="stale failure",
        )
        is None
    )

    dispatch.refresh_from_db()
    assert dispatch.status == AgentRunDispatch.STATUS_CLAIMED
    assert dispatch.claimed_by == "worker-new"
    assert dispatch.attempt_count == second_attempt

    completed = complete_agent_dispatch(
        dispatch.id,
        worker_name="worker-new",
        attempt_count=second_attempt,
        summary={"result": "current"},
    )
    assert completed is not None
    assert AgentRunEvent.objects.filter(run=run, event_type="agent_dispatch_completed").count() == 1

    dispatch.refresh_from_db()
    assert dispatch.status == AgentRunDispatch.STATUS_COMPLETED
    assert dispatch.metadata["completion_summary"] == {"result": "current"}
