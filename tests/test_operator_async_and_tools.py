"""Tests for operator async resume, mutate tools, and compose helpers."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest
from django.contrib.auth.models import User

from app.assistant_actions import get_action_spec
from core_ui.models import AssistantAction, ChatMessage, ChatSession, ChatTurnState, UserAppPermission
from core_ui.services.operator_async import (
    is_async_tool_result,
    normalize_async_ref,
    park_turn_for_async,
    resume_turns_for_agent_run,
)
from servers.operator.mutate_tools import register_operator_mutate_tools
from servers.operator.tools import register_operator_tools


def _grant(user: User, *features: str) -> None:
    for feature in features:
        UserAppPermission.objects.update_or_create(user=user, feature=feature, defaults={"allowed": True})


@pytest.mark.django_db
def test_async_result_detection():
    assert is_async_tool_result({"async": True, "run_id": 1})
    assert is_async_tool_result({"run_id": 9, "status": "running"})
    assert not is_async_tool_result({"ok": True, "output": "hi"})
    ref = normalize_async_ref({"run_id": 3, "status": "pending"}, action_type="agent.run")
    assert ref["async_kind"] == "agent_run"
    assert ref["run_id"] == 3


@pytest.mark.django_db
def test_park_and_resume_agent_run(monkeypatch):
    register_operator_tools()
    register_operator_mutate_tools()
    user = User.objects.create_user(username="async-op", password="x")
    _grant(user, "orchestrator", "servers", "agents")
    session = ChatSession.objects.create(user=user, title="async")
    user_msg = ChatMessage.objects.create(session=session, role="user", content="run agent")
    asst = ChatMessage.objects.create(session=session, role="assistant", content="starting")
    action = AssistantAction.objects.create(
        user=user,
        session=session,
        message=asst,
        action_type="agent.run",
        status=AssistantAction.STATUS_COMPLETED,
        risk="mutating",
        requires_confirmation=True,
        result_payload={"run_id": 42, "async": True, "async_kind": "agent_run", "status": "running"},
        async_run_ref={"run_id": 42, "async_kind": "agent_run", "tool_call_id": "call_x"},
    )
    turn = ChatTurnState.objects.create(
        session=session,
        user_message=user_msg,
        assistant_message=asst,
        pending_action=action,
        status=ChatTurnState.STATUS_AWAITING_CONFIRM,
        llm_messages=[{"role": "user", "content": "run agent"}],
        pending_tool_call={"id": "call_x", "name": "agent_run", "action_type": "agent.run"},
    )
    park_turn_for_async(
        turn,
        tool_call={"id": "call_x", "name": "agent_run"},
        async_ref={"async_kind": "agent_run", "run_id": 42},
        messages=list(turn.llm_messages),
        note="waiting",
    )
    turn.refresh_from_db()
    assert turn.status == ChatTurnState.STATUS_AWAITING_ASYNC

    fake_run = MagicMock()
    fake_run.pk = 42
    fake_run.status = "completed"
    fake_run.ai_analysis = "all good"

    resumed: list[Any] = []

    async def fake_resume(**kwargs):
        resumed.append(kwargs)
        return MagicMock(status=ChatTurnState.STATUS_DONE)

    monkeypatch.setattr(
        "core_ui.services.operator_session.resume_after_async_result",
        fake_resume,
    )
    monkeypatch.setattr(
        "core_ui.services.operator_async._agent_run_result_payload",
        lambda run: {"ok": True, "run_id": run.pk, "status": run.status, "async_done": True},
    )

    count = resume_turns_for_agent_run(fake_run)
    assert count == 1
    assert len(resumed) == 1
    assert resumed[0]["result_payload"]["run_id"] == 42
    assert resumed[0]["result_payload"]["ok"] is True


@pytest.mark.django_db
def test_mutate_tools_registered():
    register_operator_mutate_tools()
    assert get_action_spec("operator.run_command") is not None
    assert get_action_spec("operator.run_fanout") is not None
    assert get_action_spec("operator.save_runbook") is not None
    assert get_action_spec("operator.run_playbook") is not None
    assert get_action_spec("operator.undo_last") is not None


@pytest.mark.django_db
def test_list_servers_lookup_mode_no_ui_table_and_resolve_registered():
    """Connect/diagnose flows must not spam the inventory card; name_index always present."""
    from app.assistant_actions import AssistantActionContext
    from servers.models import Server
    from servers.operator.tools import list_servers, resolve_server

    register_operator_tools()
    assert get_action_spec("operator.resolve_server") is not None
    user = User.objects.create_user(username="inv-lookup", password="x")
    _grant(user, "servers")
    Server.objects.create(name="lunix", host="127.0.0.1", port=22, user=user, username="u")
    Server.objects.create(name="api-prod-01", host="127.0.0.1", port=22, user=user, username="u")

    # Default (no show_in_chat) → silent compact lookup, no fleet card
    bare = list_servers(AssistantActionContext(user=user, input_payload={}))
    assert bare.get("ui_table") is False
    assert bare.get("servers") == []
    assert bare["name_index"].get("lunix")

    # Explicit list intent (platform injects show_in_chat)
    listed = list_servers(AssistantActionContext(user=user, input_payload={"show_in_chat": True}))
    assert listed.get("ui_table") is True
    assert len(listed.get("servers") or []) >= 2
    assert listed.get("reply_hint")

    # Filtered lookup → no card
    filtered = list_servers(AssistantActionContext(user=user, input_payload={"q": "lunix"}))
    assert filtered.get("ui_table") is False
    assert filtered["count"] == 1
    assert filtered["servers"][0]["name"] == "lunix"

    resolved = resolve_server(AssistantActionContext(user=user, input_payload={"q": "lunix"}))
    assert resolved.get("found") is True
    assert resolved.get("ui_table") is False
    assert resolved["server_name"] == "lunix"


def test_prepare_list_servers_arguments_policy():
    from servers.operator.tools import (
        extract_server_hint,
        normalize_host_hint,
        prefer_resolve_server_for_message,
        prepare_list_servers_arguments,
        user_wants_inventory_card,
    )

    assert user_wants_inventory_card("Покажи список серверов")
    assert user_wants_inventory_card("Списко серверов")  # typo
    assert user_wants_inventory_card("Список серверов")
    assert user_wants_inventory_card("Выведи список серверов")
    assert not user_wants_inventory_card("Подключись к серверу графана и собери метрики")
    assert not user_wants_inventory_card("Проверь метрики lunix")

    listed = prepare_list_servers_arguments({}, user_message="Покажи список серверов")
    assert listed["show_in_chat"] is True
    assert "q" not in listed

    # Connect: list_servers must NOT stick a cyrillic filter (that broke the model loop)
    connect = prepare_list_servers_arguments({}, user_message="Подключись к серверу графана и собери метрики")
    assert connect["show_in_chat"] is False
    assert not connect.get("q")

    resolved = prefer_resolve_server_for_message({}, user_message="Проверь метрики сервера графаны и собери прогноз")
    assert resolved is not None
    assert resolved["q"] == "grafana"

    assert normalize_host_hint("графаны") == "grafana"
    assert extract_server_hint("метрики @lunix") == "lunix"
    assert extract_server_hint("Подключись к серверу grafana-01") == "grafana-01"
    assert extract_server_hint("Проверь метрики сервера графаны") == "grafana"


def test_compress_inventory_assistant_content():
    from core_ui.services.operator_artifacts import compress_inventory_assistant_content

    msg = MagicMock()
    msg.content = (
        "Инвентарь содержит 16 серверов:\n\n"
        "• api-prod-01, api-prod-02 — API шлюзы (prod) • bastion-01 — SSH прокси "
        "• ci-runner-01, ci-runner-02 — CI/CD агенты • db-prod-primary — БД"
    )
    msg.metadata = {
        "inventory_card": True,
        "inventory_count": 16,
        "tables": [
            {
                "kind": "servers",
                "title": "Серверы · 16",
                "items": [{"name": f"s{i}"} for i in range(16)],
                "status_counts": {"healthy": 16, "warning": 0, "critical": 0, "unreachable": 0, "unknown": 0},
            }
        ],
    }
    assert compress_inventory_assistant_content(msg) is True
    assert "API шлюз" not in msg.content
    assert "16" in msg.content
    assert "healthy" in msg.content.lower() or "ok" in msg.content.lower()
    assert msg.save.called


def test_maybe_attach_table_respects_ui_table_false():
    from core_ui.services.operator_artifacts import maybe_attach_table_metadata

    msg = MagicMock()
    msg.metadata = {}
    maybe_attach_table_metadata(
        msg,
        {
            "ok": True,
            "result": {
                "servers": [
                    {
                        "id": 1,
                        "name": "lunix",
                        "host": "127.0.0.1",
                        "port": 22,
                        "tags": [],
                        "status": "healthy",
                    }
                ],
                "count": 1,
                "ui_table": False,
            },
        },
        action_type="operator.list_servers",
    )
    assert not msg.save.called

    msg2 = MagicMock()
    msg2.metadata = {}
    maybe_attach_table_metadata(
        msg2,
        {
            "ok": True,
            "result": {
                "servers": [
                    {
                        "id": 1,
                        "name": "lunix",
                        "host": "127.0.0.1",
                        "port": 22,
                        "tags": [],
                        "status": "healthy",
                    }
                ],
                "count": 1,
                "ui_table": True,
            },
        },
        action_type="operator.list_servers",
    )
    assert msg2.save.called
    assert msg2.metadata["tables"][0]["kind"] == "servers"


@pytest.mark.django_db
def test_save_runbook_creates_playbook():
    register_operator_mutate_tools()
    from app.assistant_actions import AssistantActionContext
    from servers.models import Playbook
    from servers.operator.mutate_tools import save_runbook

    user = User.objects.create_user(username="rb-user", password="x")
    _grant(user, "servers")
    ctx = AssistantActionContext(
        user=user,
        input_payload={
            "title": "WAL cleanup",
            "steps": [
                {"command": "df -h", "description": "check disk"},
                {"command": "find /var/lib/pg -name '*.wal' | head", "description": "list wal"},
            ],
        },
    )
    result = save_runbook(ctx)
    assert result["ok"] is True
    pb = Playbook.objects.get(pk=result["playbook"]["id"])
    assert pb.name == "WAL cleanup"
    assert pb.kind == Playbook.KIND_RUNBOOK
    assert len(pb.tasks) == 2


@pytest.mark.django_db
def test_create_playbook_accepts_command_steps():
    """A runbook expressed as a step/command list must not require yaml/tasks."""
    register_operator_mutate_tools()
    from app.assistant_actions import AssistantActionContext, AssistantActionError
    from servers.models import Playbook
    from servers.operator.mutate_tools import create_playbook

    user = User.objects.create_user(username="pb-user", password="x")
    _grant(user, "servers")
    steps = [
        {"command": "docker ps -a", "description": "Run command"},
        {"command": "systemctl list-units --state=running | head -20", "description": "Run command"},
    ]
    # Model puts the runbook body under "steps" (the reported failing case).
    result = create_playbook(AssistantActionContext(user=user, input_payload={"name": "rb", "steps": steps}))
    assert result["ok"] is True
    pb = Playbook.objects.get(pk=result["playbook"]["id"])
    assert pb.kind == Playbook.KIND_RUNBOOK
    assert len(pb.tasks) == 2

    # Alternate key "commands" also works.
    alt = create_playbook(AssistantActionContext(user=user, input_payload={"name": "rb2", "commands": steps}))
    assert alt["ok"] is True and alt["playbook"]["task_count"] == 2

    # With nothing usable it still fails cleanly.
    with pytest.raises(AssistantActionError):
        create_playbook(AssistantActionContext(user=user, input_payload={"name": "empty"}))


@pytest.mark.django_db
def test_normalize_tool_arguments():
    from core_ui.services.operator_tools import normalize_tool_arguments
    from servers.models import Server

    user = User.objects.create_user(username="norm-user", password="x")
    _grant(user, "servers")
    srv = Server.objects.create(user=user, name="grafana-1", host="10.0.0.5", is_active=True)

    # Key aliases + numeric-string coercion.
    out = normalize_tool_arguments(user, "operator.run_command", {"cmd": "ls", "server_id": "7"})
    assert out == {"command": "ls", "server_id": 7}

    # Server name resolves to id; id list coerces + dedupes.
    out = normalize_tool_arguments(
        user, "operator.run_fanout", {"shell": "uptime", "servers": [str(srv.id), srv.id, "grafana-1"]}
    )
    assert out["command"] == "uptime"
    assert out["server_ids"] == [srv.id]

    # A named host collapses into server_id.
    out = normalize_tool_arguments(user, "operator.server_metrics", {"host": "grafana-1"})
    assert out["server_id"] == srv.id


@pytest.mark.django_db
def test_freeze_fanout_targets_snapshots_accessible_servers():
    from core_ui.services.operator_tools import freeze_mutating_targets
    from servers.models import Server

    user = User.objects.create_user(username="fanout-freeze", password="x")
    other = User.objects.create_user(username="fanout-other", password="x")
    _grant(user, "servers")
    prod = Server.objects.create(user=user, name="prod-1", host="10.0.0.11", tags="prod")
    Server.objects.create(user=user, name="stage-1", host="10.0.0.12", tags="stage")
    Server.objects.create(user=other, name="prod-other", host="10.0.0.13", tags="prod")

    frozen = freeze_mutating_targets(
        user,
        "operator.run_fanout",
        {"tag": "prod", "command": "uptime"},
    )
    assert frozen["server_ids"] == [prod.id]


@pytest.mark.django_db
def test_schedule_agent_applies_recurrence():
    """schedule_agent must produce a real recurring config, not a silent 'manual'."""
    from app.assistant_actions import AssistantActionContext
    from servers.models import ServerAgent
    from servers.operator.mutate_tools import schedule_agent

    user = User.objects.create_user(username="sched-user", password="x")
    _grant(user, "agents")
    agent = ServerAgent.objects.create(user=user, name="disk-check", goal="check disks", mode="mini")

    def run(payload):
        schedule_agent(AssistantActionContext(user=user, input_payload={"agent_id": agent.id, **payload}))
        agent.refresh_from_db()
        return agent.schedule_config, agent.schedule_minutes

    cfg, minutes = run({"daily_time": "09:00"})
    assert cfg["mode"] == "daily" and cfg["time"] == "09:00" and minutes == 1440

    cfg, minutes = run({"weekdays": [0, 2, 4], "daily_time": "18:30"})
    assert cfg["mode"] == "weekly" and cfg["weekdays"] == [0, 2, 4]

    cfg, minutes = run({"schedule_minutes": 30})
    assert cfg["mode"] == "interval" and cfg["interval_minutes"] == 30 and minutes == 30

    # cron: Monday 06:00 → weekly, Mon=0.
    cfg, minutes = run({"cron": "0 6 * * 1"})
    assert cfg["mode"] == "weekly" and cfg["time"] == "06:00" and cfg["weekdays"] == [0]
    assert agent.is_enabled
