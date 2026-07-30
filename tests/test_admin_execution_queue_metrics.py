from __future__ import annotations

from datetime import timedelta

import pytest
from django.contrib.auth.models import User
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from servers.models import (
    AgentRun,
    AgentRunDispatch,
    BackgroundWorkerState,
    PlaybookRun,
    PlaybookRunDispatch,
    ServerAgent,
)

pytestmark = pytest.mark.django_db


def _agent_dispatch(user: User, agent: ServerAgent, *, status: str, attempts: int) -> AgentRunDispatch:
    run = AgentRun.objects.create(user=user, agent=agent, status=AgentRun.STATUS_RUNNING)
    return AgentRunDispatch.objects.create(
        run=run,
        agent=agent,
        user=user,
        status=status,
        attempt_count=attempts,
    )


def test_admin_dashboard_exposes_queue_depth_expired_leases_and_retries():
    now = timezone.now()
    admin = User.objects.create_user(username="queue-admin", password="x", is_staff=True)
    agent = ServerAgent.objects.create(user=admin, name="Queue agent")

    queued = _agent_dispatch(admin, agent, status=AgentRunDispatch.STATUS_QUEUED, attempts=0)
    AgentRunDispatch.objects.filter(pk=queued.pk).update(queued_at=now - timedelta(minutes=7))
    expired = _agent_dispatch(admin, agent, status=AgentRunDispatch.STATUS_CLAIMED, attempts=2)
    AgentRunDispatch.objects.filter(pk=expired.pk).update(lease_expires_at=now - timedelta(seconds=5))
    exhausted = _agent_dispatch(admin, agent, status=AgentRunDispatch.STATUS_FAILED, attempts=3)
    AgentRunDispatch.objects.filter(pk=exhausted.pk).update(completed_at=now, max_attempts=3)

    playbook_run = PlaybookRun.objects.create(user=admin)
    PlaybookRunDispatch.objects.create(
        run=playbook_run,
        user=admin,
        status=PlaybookRunDispatch.STATUS_QUEUED,
        attempt_count=2,
    )
    BackgroundWorkerState.objects.create(
        worker_kind=BackgroundWorkerState.KIND_AGENT_EXECUTION,
        worker_key="stale",
        status=BackgroundWorkerState.STATUS_RUNNING,
        lease_expires_at=now - timedelta(seconds=1),
    )

    client = Client()
    client.force_login(admin)
    response = client.get(reverse("api_admin_dashboard"))

    assert response.status_code == 200
    queues = response.json()["data"]["execution_queues"]
    assert queues["depth"] == 2
    assert queues["in_flight"] == 1
    assert queues["lease_expired"] == 1
    assert queues["retrying"] == 2
    assert queues["retried_24h"] == 3
    assert queues["attempts_exhausted_24h"] == 1
    assert queues["stale_workers"] == 1
    assert queues["oldest_queued_seconds"] >= 6 * 60
    assert {item["id"] for item in queues["queues"]} == {"agents", "playbooks"}
