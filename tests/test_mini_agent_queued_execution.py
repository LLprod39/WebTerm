"""Mini agents must queue on the execution plane (never block HTTP)."""

from __future__ import annotations

import pytest
from asgiref.sync import async_to_sync
from django.contrib.auth.models import User

from servers.agent_background import execute_agent_dispatch
from servers.agent_dispatch import claim_next_agent_dispatch, enqueue_agent_run_dispatch
from servers.models import AgentRun, AgentRunDispatch, Server, ServerAgent


def _create_server(user: User) -> Server:
    return Server.objects.create(
        user=user,
        name="mini-queue-srv",
        host="10.20.30.40",
        username="root",
        auth_method="password",
    )


@pytest.mark.django_db
def test_mini_agent_dispatch_executes_via_run_agent(monkeypatch):
    user = User.objects.create_user(username="mini-queue-user", password="x")
    server = _create_server(user)
    agent = ServerAgent.objects.create(
        user=user,
        name="Mini Queued",
        mode=ServerAgent.MODE_MINI,
        agent_type=ServerAgent.TYPE_CUSTOM,
        commands=["uname -a"],
    )
    agent.servers.set([server])

    run = AgentRun.objects.create(
        agent=agent,
        server=server,
        user=user,
        status=AgentRun.STATUS_PENDING,
    )
    dispatch = enqueue_agent_run_dispatch(
        run=run,
        agent_id=agent.id,
        user_id=user.id,
        server_ids=[server.id],
        plan_only=False,
    )

    async def fake_run_agent(agent_obj, server_obj, user_obj, *, run_record=None):
        from asgiref.sync import sync_to_async

        target = run_record
        if target is None:
            target = await sync_to_async(AgentRun.objects.create)(
                agent=agent_obj,
                server=server_obj,
                user=user_obj,
                status=AgentRun.STATUS_RUNNING,
            )

        def _complete():
            target.status = AgentRun.STATUS_COMPLETED
            target.ai_analysis = "queued mini ok"
            target.commands_output = [{"cmd": "uname -a", "stdout": "Linux", "stderr": "", "exit_code": 0}]
            target.save(update_fields=["status", "ai_analysis", "commands_output"])

        await sync_to_async(_complete)()
        return target

    monkeypatch.setattr("servers.agents.run_agent", fake_run_agent)

    claimed = claim_next_agent_dispatch(worker_name="test-worker", lease_seconds=60)
    assert claimed is not None
    assert claimed.id == dispatch.id

    async_to_sync(execute_agent_dispatch)(dispatch.id, worker_key="test-worker", lease_seconds=60)

    run.refresh_from_db()
    dispatch.refresh_from_db()
    assert run.status == AgentRun.STATUS_COMPLETED
    assert run.ai_analysis == "queued mini ok"
    assert dispatch.status == AgentRunDispatch.STATUS_COMPLETED
