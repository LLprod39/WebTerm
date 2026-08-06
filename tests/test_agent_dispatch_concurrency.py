from __future__ import annotations

import pytest
from django.contrib.auth.models import User

from servers.agents.agent_dispatch import claim_next_agent_dispatch, enqueue_agent_run_dispatch
from servers.models_agents import AgentRun, AgentRunDispatch, ServerAgent


def _enqueue(user: User, agent: ServerAgent) -> AgentRunDispatch:
    run = AgentRun.objects.create(agent=agent, user=user, status=AgentRun.STATUS_PENDING)
    return enqueue_agent_run_dispatch(
        run=run,
        agent_id=agent.id,
        user_id=user.id,
        server_ids=[],
        plan_only=False,
    )


@pytest.mark.django_db(transaction=True)
def test_agent_claims_are_fair_across_users_before_second_slot(monkeypatch):
    users = [User.objects.create_user(username=f"fair-agent-user-{index}") for index in range(3)]
    agents = [
        ServerAgent.objects.create(
            user=user,
            name=f"Fair agent {index}",
            mode=ServerAgent.MODE_MINI,
            agent_type=ServerAgent.TYPE_CUSTOM,
        )
        for index, user in enumerate(users)
    ]
    _enqueue(users[0], agents[0])
    _enqueue(users[0], agents[0])
    _enqueue(users[1], agents[1])
    _enqueue(users[1], agents[1])
    _enqueue(users[2], agents[2])
    monkeypatch.setattr("servers.agents.agent_dispatch._refresh_run_report_payload", lambda *_args: None)

    claimed = [
        claim_next_agent_dispatch(
            worker_name=f"fair-worker-{index}",
            global_concurrency=3,
            per_user_concurrency=2,
        )
        for index in range(3)
    ]

    assert all(dispatch is not None for dispatch in claimed)
    assert {dispatch.user_id for dispatch in claimed if dispatch is not None} == {user.id for user in users}


@pytest.mark.django_db(transaction=True)
def test_agent_claims_enforce_global_and_per_user_capacity(monkeypatch):
    user_a = User.objects.create_user(username="capacity-agent-a")
    user_b = User.objects.create_user(username="capacity-agent-b")
    agent_a = ServerAgent.objects.create(
        user=user_a,
        name="Capacity agent A",
        mode=ServerAgent.MODE_MINI,
        agent_type=ServerAgent.TYPE_CUSTOM,
    )
    agent_b = ServerAgent.objects.create(
        user=user_b,
        name="Capacity agent B",
        mode=ServerAgent.MODE_MINI,
        agent_type=ServerAgent.TYPE_CUSTOM,
    )
    for _index in range(3):
        _enqueue(user_a, agent_a)
        _enqueue(user_b, agent_b)
    monkeypatch.setattr("servers.agents.agent_dispatch._refresh_run_report_payload", lambda *_args: None)

    first = claim_next_agent_dispatch(worker_name="capacity-1", global_concurrency=2, per_user_concurrency=1)
    second = claim_next_agent_dispatch(worker_name="capacity-2", global_concurrency=2, per_user_concurrency=1)
    blocked = claim_next_agent_dispatch(worker_name="capacity-3", global_concurrency=2, per_user_concurrency=1)

    assert first is not None
    assert second is not None
    assert first.user_id != second.user_id
    assert blocked is None
