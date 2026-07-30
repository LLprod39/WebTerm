"""Regression coverage for exact server capability enforcement."""

from __future__ import annotations

import json

import pytest
from asgiref.sync import async_to_sync
from django.contrib.auth.models import User
from django.test import Client

from app.assistant_actions import AssistantActionContext, AssistantActionError
from core_ui.models import UserAppPermission
from core_ui.services.operator_memory import save_lesson_from_operator
from servers.agents.agent_background import execute_agent_dispatch
from servers.agents.agent_dispatch import claim_next_agent_dispatch, enqueue_agent_run_dispatch
from servers.agents.agent_launch import launch_queued_agent_run
from servers.models import AgentRun, AgentRunDispatch, Server, ServerAgent, ServerShare
from servers.operator.mutate_exec import run_command, run_fanout
from servers.operator.tools_actions import server_memory
from servers.services.server_query import get_servers_for_user


def _server(owner: User, *, name: str = "shared-capability-server") -> Server:
    return Server.objects.create(
        user=owner,
        name=name,
        host="10.40.0.10",
        username="root",
        auth_method="key",
    )


def _share(owner: User, teammate: User, server: Server, **capabilities) -> ServerShare:
    return ServerShare.objects.create(
        server=server,
        user=teammate,
        shared_by=owner,
        **capabilities,
    )


@pytest.mark.django_db
def test_agent_launch_requires_execute_command_capability(monkeypatch):
    owner = User.objects.create_user(username="agent-server-owner", password="x")
    teammate = User.objects.create_user(username="agent-shared-user", password="x")
    server = _server(owner)
    share = _share(
        owner,
        teammate,
        server,
        can_connect_terminal=True,
        can_execute_command=False,
    )
    agent = ServerAgent.objects.create(
        user=teammate,
        name="Shared Server Agent",
        mode=ServerAgent.MODE_FULL,
        goal="Inspect the shared server",
    )
    agent.servers.set([server])
    launched: list[dict] = []
    monkeypatch.setattr(
        "servers.agents.agent_launch.launch_agent_run_background", lambda **kwargs: launched.append(kwargs)
    )

    denied = launch_queued_agent_run(
        agent=agent,
        user=teammate,
        accessible_servers_queryset=get_servers_for_user(teammate),
    )

    assert denied == {
        "ok": False,
        "status": 403,
        "error": "Missing server capability: execute_command",
    }
    assert launched == []
    assert not AgentRun.objects.filter(agent=agent).exists()

    share.can_execute_command = True
    share.save(update_fields=["can_execute_command", "updated_at"])
    allowed = launch_queued_agent_run(
        agent=agent,
        user=teammate,
        accessible_servers_queryset=get_servers_for_user(teammate),
    )

    assert allowed["ok"] is True
    assert [item["server_ids"] for item in launched] == [[server.id]]


@pytest.mark.django_db
def test_agent_assignment_requires_execute_command_capability():
    owner = User.objects.create_user(username="agent-assignment-owner", password="x")
    teammate = User.objects.create_user(username="agent-assignment-user", password="x")
    server = _server(owner, name="agent-assignment-server")
    _share(owner, teammate, server, can_connect_terminal=True, can_execute_command=False)
    UserAppPermission.objects.create(user=teammate, feature="agents", allowed=True)
    client = Client()
    client.force_login(teammate)

    response = client.post(
        "/servers/api/agents/create/",
        data=json.dumps(
            {
                "name": "Denied assignment",
                "mode": ServerAgent.MODE_FULL,
                "goal": "Must not attach this server",
                "server_ids": [server.id],
            }
        ),
        content_type="application/json",
    )

    assert response.status_code == 403
    assert "execute_command" in response.json()["error"]
    assert not ServerAgent.objects.filter(user=teammate).exists()


@pytest.mark.django_db(transaction=True)
def test_agent_worker_reauthorizes_execute_command_before_engine(monkeypatch):
    owner = User.objects.create_user(username="worker-server-owner", password="x")
    teammate = User.objects.create_user(username="worker-shared-user", password="x")
    server = _server(owner, name="worker-shared-server")
    share = _share(owner, teammate, server, can_execute_command=True)
    agent = ServerAgent.objects.create(
        user=teammate,
        name="Revoked Worker Agent",
        mode=ServerAgent.MODE_FULL,
        goal="Must not execute after revocation",
    )
    agent.servers.set([server])
    run = AgentRun.objects.create(
        agent=agent,
        server=server,
        user=teammate,
        status=AgentRun.STATUS_PENDING,
    )
    dispatch = enqueue_agent_run_dispatch(
        run=run,
        agent_id=agent.id,
        user_id=teammate.id,
        server_ids=[server.id],
        plan_only=False,
    )
    share.can_execute_command = False
    share.save(update_fields=["can_execute_command", "updated_at"])
    claimed = claim_next_agent_dispatch(worker_name="capability-test", lease_seconds=60)
    assert claimed is not None
    assert claimed.pk == dispatch.pk

    async def forbidden_engine_run(*_args, **_kwargs):
        pytest.fail("agent engine must not run after execute_command is revoked")

    monkeypatch.setattr("servers.agents.agent_background.AgentEngine.run", forbidden_engine_run)

    with pytest.raises(PermissionError, match="execute_command"):
        async_to_sync(execute_agent_dispatch)(dispatch.id, worker_key="capability-test", lease_seconds=60)

    dispatch.refresh_from_db()
    run.refresh_from_db()
    assert dispatch.status == AgentRunDispatch.STATUS_FAILED
    assert run.status == AgentRun.STATUS_FAILED


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize(
    ("handler", "payload"),
    [
        (run_command, {"server_id": None, "command": "uptime"}),
        (run_fanout, {"server_ids": [], "command": "uptime"}),
    ],
)
def test_operator_commands_require_execute_command_capability(monkeypatch, handler, payload):
    owner = User.objects.create_user(username=f"operator-owner-{handler.__name__}", password="x")
    teammate = User.objects.create_user(username=f"operator-user-{handler.__name__}", password="x")
    server = _server(owner, name=f"operator-server-{handler.__name__}")
    _share(owner, teammate, server, can_connect_terminal=True, can_execute_command=False)
    payload = dict(payload)
    if handler is run_command:
        payload["server_id"] = server.id
    else:
        payload["server_ids"] = [server.id]
    sink_calls: list[int] = []

    async def forbidden_run(*_args, **_kwargs):
        sink_calls.append(server.id)
        return {"stdout": "unexpected", "stderr": "", "exit_status": 0}

    monkeypatch.setattr("servers.linux_ui_runtime._run_command_result", forbidden_run)

    result = handler(AssistantActionContext(user=teammate, input_payload=payload))
    rows = result.get("matrix") or [result]

    assert sink_calls == []
    assert rows[0]["ok"] is False
    assert "execute_command" in rows[0]["error"]


@pytest.mark.django_db
def test_operator_memory_read_requires_view_context(monkeypatch):
    owner = User.objects.create_user(username="memory-read-owner", password="x")
    teammate = User.objects.create_user(username="memory-read-user", password="x")
    server = _server(owner, name="memory-read-server")
    _share(owner, teammate, server, share_context=False)
    monkeypatch.setattr(
        "core_ui.services.operator_memory.memory_hints_for_server",
        lambda *_args, **_kwargs: pytest.fail("memory provider must not be called without view_context"),
    )

    with pytest.raises(AssistantActionError, match="view_context") as exc_info:
        server_memory(AssistantActionContext(user=teammate, input_payload={"server_id": server.id}))

    assert exc_info.value.status == 403


@pytest.mark.django_db
def test_operator_memory_write_is_owner_only(monkeypatch):
    owner = User.objects.create_user(username="memory-write-owner", password="x")
    teammate = User.objects.create_user(username="memory-write-user", password="x")
    server = _server(owner, name="memory-write-server")
    _share(owner, teammate, server, share_context=True)
    sink_calls: list[int] = []

    def fake_ingest(*, server_id, **_kwargs):
        sink_calls.append(server_id)
        return {"server_id": server_id}

    monkeypatch.setattr("core_ui.services.operator_memory._ingest_lesson_to_server", fake_ingest)

    with pytest.raises(PermissionError, match="owned"):
        save_lesson_from_operator(
            user=teammate,
            title="Shared lesson",
            lesson="Must not mutate the owner's memory",
            server_ids=[server.id],
        )
    assert sink_calls == []

    allowed = save_lesson_from_operator(
        user=owner,
        title="Owner lesson",
        lesson="Owner may update owned server memory",
        server_ids=[server.id],
    )
    assert allowed["count"] == 1
    assert sink_calls == [server.id]
