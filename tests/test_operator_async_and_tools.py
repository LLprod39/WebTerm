"""Tests for operator async resume, mutate tools, and compose helpers."""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import MagicMock, patch

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
from servers.operator_mutate_tools import register_operator_mutate_tools
from servers.operator_tools import register_operator_tools


def _grant(user: User, *features: str) -> None:
    for feature in features:
        UserAppPermission.objects.update_or_create(
            user=user, feature=feature, defaults={"allowed": True}
        )


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
def test_save_runbook_creates_playbook():
    register_operator_mutate_tools()
    from app.assistant_actions import AssistantActionContext
    from servers.models import Playbook
    from servers.operator_mutate_tools import save_runbook

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
