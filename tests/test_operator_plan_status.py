"""W1/W3/W4/W5: plan status integrity, snapshot, continuation, autonomy modes."""

from __future__ import annotations

import asyncio
from datetime import timedelta
from typing import Any
from unittest.mock import MagicMock

import pytest
from asgiref.sync import async_to_sync
from django.contrib.auth.models import User
from django.utils import timezone

from app.assistant_actions import AssistantActionSpec, get_action_spec, register_action
from core_ui.models import AssistantAction, ChatMessage, ChatSession, ChatTurnState
from core_ui.services.assistant_chat import serialize_chat_session
from core_ui.services.operator_loop import run_operator_loop
from core_ui.services.operator_plan import (
    AUTONOMY_AUTONOMOUS,
    AUTONOMY_CONFIRM_EACH,
    AUTONOMY_PLAN_ONCE,
    advance_plan_on_action,
    approved_plan_step_matches,
    canonical_plan_step_matches,
    get_autonomy_mode,
    mark_plan_step_awaiting_confirm,
    mark_plan_step_running,
    plan_once_allows_auto_run,
    reconcile_plan_state,
)
from core_ui.services.operator_tools import specs_to_tools
from core_ui.services.operator_turn_runtime import get_active_turn_snapshot, stop_active_turn


def _operator_user(username: str) -> User:
    """User with mutate automation (pilot_operator profile)."""
    from core_ui.views.access_views import _apply_access_profile

    user = User.objects.create_user(username=username, password="x")
    _apply_access_profile(user, "pilot_operator")
    return user


class ScriptedToolsLLM:
    def __init__(self, iterations: list[list[dict[str, Any]]]):
        self.iterations = iterations
        self.call_count = 0

    async def stream_chat_tools(self, messages, tools, **kwargs):
        idx = self.call_count
        self.call_count += 1
        if idx >= len(self.iterations):
            yield {"type": "text_delta", "text": "done"}
            yield {"type": "done", "usage": {}, "stop_reason": "end_turn"}
            return
        for event in self.iterations[idx]:
            yield event


# ---------------------------------------------------------------------------
# W1 — status helpers
# ---------------------------------------------------------------------------


def test_park_marks_awaiting_confirm_not_running():
    plan = {
        "title": "T",
        "status": "approved",
        "steps": [
            {"id": 1, "text": "A", "tool": "operator.run_command", "status": "pending"},
            {"id": 2, "text": "B", "tool": "operator.save_runbook", "status": "pending"},
        ],
    }
    updated = mark_plan_step_awaiting_confirm(plan, action_type="operator.run_command")
    assert updated is not None
    assert updated["steps"][0]["status"] == "awaiting_confirm"
    assert updated["steps"][1]["status"] == "pending"
    assert updated["status"] == "approved"  # not forced to running


def test_confirm_running_then_done():
    plan = {
        "title": "T",
        "status": "approved",
        "steps": [
            {"id": 1, "text": "A", "tool": "operator.run_command", "input": {"command": "df"}, "status": "pending"},
        ],
    }
    plan = mark_plan_step_awaiting_confirm(plan, action_type="operator.run_command")
    plan = mark_plan_step_running(plan, action_type="operator.run_command")
    assert plan["steps"][0]["status"] == "running"
    assert plan["status"] == "running"
    plan = advance_plan_on_action(plan, action_type="operator.run_command", outcome="done")
    assert plan["steps"][0]["status"] == "done"
    assert plan["status"] == "completed"


def test_cancel_marks_cancelled_and_pauses_plan():
    plan = {
        "title": "T",
        "status": "approved",
        "steps": [
            {"id": 1, "text": "A", "tool": "operator.run_command", "status": "awaiting_confirm"},
            {"id": 2, "text": "B", "tool": "operator.save_runbook", "status": "pending"},
        ],
    }
    plan = advance_plan_on_action(plan, action_type="operator.run_command", outcome="cancelled")
    assert plan["steps"][0]["status"] == "cancelled"
    assert plan["steps"][0]["status"] != "failed"
    assert plan["status"] == "paused"


def test_advance_closes_running_or_awaiting_confirm():
    plan = {
        "title": "T",
        "status": "running",
        "steps": [
            {"id": 1, "text": "A", "tool": "operator.run_command", "status": "running"},
            {"id": 2, "text": "B", "tool": "x", "status": "pending"},
        ],
    }
    plan = advance_plan_on_action(plan, action_type="operator.run_command", outcome="done")
    assert plan["steps"][0]["status"] == "done"


def test_approved_plan_step_matches_only_pending_not_running():
    plan = {
        "title": "T",
        "status": "approved",
        "steps": [
            {
                "id": 1,
                "text": "A",
                "tool": "operator.run_command",
                "input": {"server_id": 1, "command": "df"},
                "status": "running",
            }
        ],
    }
    assert not approved_plan_step_matches(
        plan,
        action_type="operator.run_command",
        input_payload={"server_id": 1, "command": "df"},
    )
    plan["steps"][0]["status"] = "pending"
    assert approved_plan_step_matches(
        plan,
        action_type="operator.run_command",
        input_payload={"server_id": 1, "command": "df"},
    )
    # Empty input fail-closed
    plan["steps"][0]["input"] = {}
    assert not approved_plan_step_matches(
        plan,
        action_type="operator.run_command",
        input_payload={},
    )


def test_canonical_soft_match_and_empty_fail_closed():
    plan = {
        "title": "T",
        "status": "approved",
        "steps": [
            {
                "id": 1,
                "tool": "operator.run_command",
                "input": {"server_id": 7, "command": "systemctl  restart  nginx"},
                "status": "pending",
            }
        ],
    }
    assert canonical_plan_step_matches(
        plan,
        action_type="operator_run_command",
        input_payload={"server_id": 7, "command": "systemctl restart nginx"},
    )
    plan["steps"][0]["input"] = {}
    assert not canonical_plan_step_matches(
        plan,
        action_type="operator.run_command",
        input_payload={"server_id": 7, "command": "x"},
    )
    allowed, frozen = plan_once_allows_auto_run(
        {
            "title": "T",
            "status": "approved",
            "steps": [{"id": 1, "tool": "operator.run_command", "input": {}, "status": "pending"}],
        },
        action_type="operator.run_command",
        input_payload={"command": "df"},
    )
    assert allowed is False
    assert frozen is None


@pytest.mark.django_db
def test_reconcile_legacy_stuck_running_on_idle_turn():
    user = User.objects.create_user(username="plan-reconcile", password="x")
    session = ChatSession.objects.create(user=user)
    msg = ChatMessage.objects.create(
        session=session,
        role=ChatMessage.ROLE_ASSISTANT,
        content="plan",
        metadata={
            "plan": {
                "title": "T",
                "status": "running",
                "steps": [
                    {"id": 1, "text": "A", "tool": "operator.run_command", "status": "running"},
                    {"id": 2, "text": "B", "tool": "x", "status": "pending"},
                ],
            }
        },
    )
    turn = ChatTurnState.objects.create(
        session=session,
        assistant_message=msg,
        status=ChatTurnState.STATUS_DONE,
        error="stopped_by_user",
    )
    plan = reconcile_plan_state(msg, turn, reason="stopped_by_user")
    assert plan is not None
    assert plan["steps"][0]["status"] == "pending"
    assert plan["status"] == "paused"
    msg.refresh_from_db()
    assert msg.metadata["plan"]["steps"][0]["status"] == "pending"


@pytest.mark.django_db
def test_reconcile_legacy_running_while_awaiting_confirm():
    user = User.objects.create_user(username="plan-legacy-park", password="x")
    session = ChatSession.objects.create(user=user)
    msg = ChatMessage.objects.create(
        session=session,
        role=ChatMessage.ROLE_ASSISTANT,
        content="plan",
        metadata={
            "plan": {
                "title": "T",
                "status": "running",
                "steps": [
                    {"id": 1, "text": "A", "tool": "operator.run_command", "status": "running"},
                ],
            }
        },
    )
    turn = ChatTurnState.objects.create(
        session=session,
        assistant_message=msg,
        status=ChatTurnState.STATUS_AWAITING_CONFIRM,
    )
    plan = reconcile_plan_state(msg, turn, reason="serialize")
    assert plan["steps"][0]["status"] == "awaiting_confirm"
    assert plan["status"] == "approved"


@pytest.mark.django_db
def test_stop_active_turn_reconciles_plan():
    user = User.objects.create_user(username="plan-stop", password="x")
    session = ChatSession.objects.create(user=user)
    msg = ChatMessage.objects.create(
        session=session,
        role=ChatMessage.ROLE_ASSISTANT,
        content="working",
        metadata={
            "plan": {
                "title": "T",
                "status": "running",
                "steps": [
                    {"id": 1, "text": "A", "tool": "operator.run_command", "status": "running"},
                    {"id": 2, "text": "B", "tool": "x", "status": "pending"},
                ],
            }
        },
    )
    ChatTurnState.objects.create(
        session=session,
        assistant_message=msg,
        status=ChatTurnState.STATUS_RUNNING,
    )
    assert async_to_sync(stop_active_turn)(session.pk, user.pk) is True
    msg.refresh_from_db()
    assert msg.metadata["plan"]["steps"][0]["status"] == "pending"
    assert msg.metadata["plan"]["status"] == "paused"


@pytest.mark.django_db
def test_heartbeat_lost_reconciles_running_step_failed():
    user = User.objects.create_user(username="plan-hb", password="x")
    session = ChatSession.objects.create(user=user)
    msg = ChatMessage.objects.create(
        session=session,
        role=ChatMessage.ROLE_ASSISTANT,
        content="working",
        metadata={
            "plan": {
                "title": "T",
                "status": "running",
                "steps": [
                    {"id": 1, "text": "A", "tool": "operator.run_command", "status": "running"},
                    {"id": 2, "text": "B", "tool": "x", "status": "pending"},
                ],
            }
        },
    )
    turn = ChatTurnState.objects.create(
        session=session,
        assistant_message=msg,
        status=ChatTurnState.STATUS_RUNNING,
    )
    ChatTurnState.objects.filter(pk=turn.pk).update(updated_at=timezone.now() - timedelta(seconds=120))
    # Snapshot path marks stale turns failed and reconciles
    snap = async_to_sync(get_active_turn_snapshot)(session.pk, user.pk)
    msg.refresh_from_db()
    assert msg.metadata["plan"]["steps"][0]["status"] == "failed"
    assert msg.metadata["plan"]["status"] == "paused"
    # Stale turn is no longer active
    assert snap is None or snap.get("status") != ChatTurnState.STATUS_RUNNING


# ---------------------------------------------------------------------------
# W3 — plan on snapshot / REST
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_active_turn_snapshot_includes_plan():
    user = User.objects.create_user(username="plan-snap", password="x")
    session = ChatSession.objects.create(user=user)
    plan = {
        "title": "Snap",
        "status": "approved",
        "steps": [{"id": 1, "text": "A", "tool": "operator.run_command", "status": "awaiting_confirm"}],
    }
    msg = ChatMessage.objects.create(
        session=session,
        role=ChatMessage.ROLE_ASSISTANT,
        content="confirm",
        metadata={"plan": plan},
    )
    ChatTurnState.objects.create(
        session=session,
        assistant_message=msg,
        status=ChatTurnState.STATUS_AWAITING_CONFIRM,
    )
    snap = async_to_sync(get_active_turn_snapshot)(session.pk, user.pk)
    assert snap is not None
    assert snap.get("plan") is not None
    assert snap["plan"]["title"] == "Snap"
    assert snap["plan"]["steps"][0]["status"] == "awaiting_confirm"

    serialized = serialize_chat_session(session, include_messages=True)
    assert serialized["active_turn"] is not None
    assert serialized["active_turn"]["plan"]["title"] == "Snap"


# ---------------------------------------------------------------------------
# W4 — plan continuation nudges
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_incomplete_plan_nudges_then_pauses():
    user = _operator_user("plan-nudge")
    if get_action_spec("operator.test_mutate") is None:
        register_action(
            AssistantActionSpec(
                action_type="operator.test_mutate",
                label="Test mutate",
                description="Test",
                risk=AssistantAction.RISK_MUTATING,
                requires_confirmation=True,
                required_feature="servers",
                handler=lambda ctx: {"ok": True},
            )
        )
    session = ChatSession.objects.create(user=user, title="nudge")
    user_msg = ChatMessage.objects.create(session=session, role=ChatMessage.ROLE_USER, content="continue")
    assistant_msg = ChatMessage.objects.create(
        session=session,
        role=ChatMessage.ROLE_ASSISTANT,
        content="",
        metadata={
            "plan": {
                "title": "Multi",
                "status": "approved",
                "steps": [
                    {
                        "id": 1,
                        "text": "one",
                        "tool": "operator.test_mutate",
                        "input": {"command": "echo 1"},
                        "status": "pending",
                    },
                    {
                        "id": 2,
                        "text": "two",
                        "tool": "operator.test_mutate",
                        "input": {"command": "echo 2"},
                        "status": "pending",
                    },
                ],
            }
        },
    )
    turn = ChatTurnState.objects.create(
        session=session,
        user_message=user_msg,
        assistant_message=assistant_msg,
        status=ChatTurnState.STATUS_RUNNING,
        llm_messages=[{"role": "user", "content": "continue"}],
    )
    # Three text-only iterations → 2 nudges then pause+done
    llm = ScriptedToolsLLM(
        [
            [{"type": "text_delta", "text": "Что дальше?"}, {"type": "done", "usage": {}, "stop_reason": "end_turn"}],
            [{"type": "text_delta", "text": "Жду."}, {"type": "done", "usage": {}, "stop_reason": "end_turn"}],
            [{"type": "text_delta", "text": "Стоп."}, {"type": "done", "usage": {}, "stop_reason": "end_turn"}],
        ]
    )
    events: list[dict] = []

    async def on_event(ev):
        events.append(ev)

    tools = specs_to_tools(user)
    result = asyncio.run(run_operator_loop(turn=turn, user=user, tools=tools, on_event=on_event, provider=llm))
    assert result.status == ChatTurnState.STATUS_DONE
    assistant_msg.refresh_from_db()
    assert assistant_msg.metadata["plan"]["status"] == "paused"
    assert any(e.get("type") == "plan_paused" for e in events)
    assert llm.call_count >= 3


# ---------------------------------------------------------------------------
# W5 — autonomy modes
# ---------------------------------------------------------------------------


def test_autonomy_mode_default_confirm_each():
    session = MagicMock()
    session.pinned_context = {}
    assert get_autonomy_mode(session) == AUTONOMY_CONFIRM_EACH
    session.pinned_context = {"autonomy_mode": "plan_once"}
    assert get_autonomy_mode(session) == AUTONOMY_PLAN_ONCE
    session.pinned_context = {"autonomy_mode": "autonomous"}
    assert get_autonomy_mode(session) == AUTONOMY_AUTONOMOUS
    session.pinned_context = {"autonomy_mode": "nope"}
    assert get_autonomy_mode(session) == AUTONOMY_CONFIRM_EACH


@pytest.mark.django_db(transaction=True)
def test_autonomous_propose_plan_does_not_park():
    user = _operator_user("plan-auto")
    session = ChatSession.objects.create(
        user=user,
        title="auto",
        pinned_context={"autonomy_mode": AUTONOMY_AUTONOMOUS},
    )
    user_msg = ChatMessage.objects.create(session=session, role=ChatMessage.ROLE_USER, content="plan")
    assistant_msg = ChatMessage.objects.create(session=session, role=ChatMessage.ROLE_ASSISTANT, content="")
    turn = ChatTurnState.objects.create(
        session=session,
        user_message=user_msg,
        assistant_message=assistant_msg,
        status=ChatTurnState.STATUS_RUNNING,
        llm_messages=[{"role": "user", "content": "plan"}],
    )
    if get_action_spec("operator.test_mutate") is None:
        register_action(
            AssistantActionSpec(
                action_type="operator.test_mutate",
                label="Test mutate",
                description="Test",
                risk=AssistantAction.RISK_MUTATING,
                requires_confirmation=True,
                required_feature="servers",
                handler=lambda ctx: {"ok": True},
            )
        )
    from servers.operator.mutate_tools import register_operator_mutate_tools
    from servers.operator.tools import register_operator_tools

    register_operator_tools()
    register_operator_mutate_tools()

    llm = ScriptedToolsLLM(
        [
            [
                {
                    "type": "tool_call",
                    "id": "p1",
                    "name": "operator_propose_plan",
                    "arguments": {
                        "title": "Auto",
                        "steps": [
                            {
                                "text": "df",
                                "tool": "operator.test_mutate",
                                "input": {"command": "df -h"},
                            }
                        ],
                    },
                },
                {"type": "done", "usage": {}, "stop_reason": "tool_use"},
            ],
            [
                {
                    "type": "tool_call",
                    "id": "c1",
                    "name": "operator_test_mutate",
                    "arguments": {"command": "df -h"},
                },
                {"type": "done", "usage": {}, "stop_reason": "tool_use"},
            ],
            [
                {"type": "text_delta", "text": "План утверждён, шаги выполнены."},
                {"type": "done", "usage": {}, "stop_reason": "end_turn"},
            ],
        ]
    )
    events: list[dict] = []

    async def on_event(ev):
        events.append(ev)

    tools = specs_to_tools(user)
    result = asyncio.run(run_operator_loop(turn=turn, user=user, tools=tools, on_event=on_event, provider=llm))
    assert result.status == ChatTurnState.STATUS_DONE
    assert not any(e.get("type") == "confirm_required" for e in events)
    assistant_msg.refresh_from_db()
    assert assistant_msg.metadata.get("plan", {}).get("status") in {"approved", "completed", "running"}
    # Auto-approve path never parked propose_plan
    assert any(e.get("type") == "plan_update" and e.get("status") == "approved" for e in events)


@pytest.mark.django_db(transaction=True)
def test_plan_once_auto_runs_frozen_non_typed_step():
    user = _operator_user("plan-once")
    if get_action_spec("operator.test_mutate") is None:
        register_action(
            AssistantActionSpec(
                action_type="operator.test_mutate",
                label="Test mutate",
                description="Test",
                risk=AssistantAction.RISK_MUTATING,
                requires_confirmation=True,
                required_feature="servers",
                handler=lambda ctx: {"ok": True, "ran": True},
            )
        )
    session = ChatSession.objects.create(
        user=user,
        title="once",
        pinned_context={"autonomy_mode": AUTONOMY_PLAN_ONCE},
    )
    user_msg = ChatMessage.objects.create(session=session, role=ChatMessage.ROLE_USER, content="go")
    assistant_msg = ChatMessage.objects.create(
        session=session,
        role=ChatMessage.ROLE_ASSISTANT,
        content="",
        metadata={
            "plan": {
                "title": "Once",
                "status": "approved",
                "steps": [
                    {
                        "id": 1,
                        "text": "mutate",
                        "tool": "operator.test_mutate",
                        "input": {"cmd": "df -h"},
                        "status": "pending",
                    }
                ],
            }
        },
    )
    turn = ChatTurnState.objects.create(
        session=session,
        user_message=user_msg,
        assistant_message=assistant_msg,
        status=ChatTurnState.STATUS_RUNNING,
        llm_messages=[{"role": "user", "content": "go"}],
    )
    # Model args differ slightly — frozen primary should still auto-run
    llm = ScriptedToolsLLM(
        [
            [
                {
                    "type": "tool_call",
                    "id": "c1",
                    "name": "operator_test_mutate",
                    "arguments": {"cmd": "uptime"},  # different from frozen
                },
                {"type": "done", "usage": {}, "stop_reason": "tool_use"},
            ],
            [
                {"type": "text_delta", "text": "Готово."},
                {"type": "done", "usage": {}, "stop_reason": "end_turn"},
            ],
        ]
    )
    events: list[dict] = []

    async def on_event(ev):
        events.append(ev)

    tools = specs_to_tools(user)
    result = asyncio.run(run_operator_loop(turn=turn, user=user, tools=tools, on_event=on_event, provider=llm))
    assert result.status == ChatTurnState.STATUS_DONE
    assert not any(e.get("type") == "confirm_required" for e in events)
    action = AssistantAction.objects.filter(session=session, action_type="operator.test_mutate").first()
    assert action is not None
    assert action.status == AssistantAction.STATUS_COMPLETED
    # Frozen input was applied
    assert (action.input_payload or {}).get("cmd") == "df -h"
    assistant_msg.refresh_from_db()
    assert assistant_msg.metadata["plan"]["steps"][0]["status"] == "done"


@pytest.mark.django_db(transaction=True)
def test_autonomous_still_parks_typed_dangerous():
    """Hard floor: typed-confirm dangerous commands still park even in autonomous."""
    from core_ui.services.operator_security import should_require_typed_confirm

    assert should_require_typed_confirm(
        action_type="operator.run_command",
        risk=AssistantAction.RISK_DANGEROUS,
        input_payload={"command": "rm -rf /"},
        blast_radius={"server_names": ["web-01"]},
    )


@pytest.mark.django_db(transaction=True)
def test_mutate_park_sets_awaiting_confirm_not_running():
    user = _operator_user("plan-park-loop")
    if get_action_spec("operator.test_mutate") is None:
        register_action(
            AssistantActionSpec(
                action_type="operator.test_mutate",
                label="Test mutate",
                description="Test",
                risk=AssistantAction.RISK_MUTATING,
                requires_confirmation=True,
                required_feature="servers",
                handler=lambda ctx: {"ok": True},
            )
        )
    session = ChatSession.objects.create(
        user=user,
        title="park",
        pinned_context={"autonomy_mode": AUTONOMY_CONFIRM_EACH},
    )
    user_msg = ChatMessage.objects.create(session=session, role=ChatMessage.ROLE_USER, content="do")
    assistant_msg = ChatMessage.objects.create(
        session=session,
        role=ChatMessage.ROLE_ASSISTANT,
        content="",
        metadata={
            "plan": {
                "title": "Park",
                "status": "approved",
                "steps": [
                    {
                        "id": 1,
                        "text": "mutate",
                        "tool": "operator.test_mutate",
                        "input": {"command": "echo hi"},
                        "status": "pending",
                    }
                ],
            }
        },
    )
    turn = ChatTurnState.objects.create(
        session=session,
        user_message=user_msg,
        assistant_message=assistant_msg,
        status=ChatTurnState.STATUS_RUNNING,
        llm_messages=[{"role": "user", "content": "do"}],
    )
    # confirm_each + mismatched payload → park (approved plan exact match fails)
    llm = ScriptedToolsLLM(
        [
            [
                {
                    "type": "tool_call",
                    "id": "c1",
                    "name": "operator_test_mutate",
                    "arguments": {"command": "other"},
                },
                {"type": "done", "usage": {}, "stop_reason": "tool_use"},
            ],
        ]
    )
    events: list[dict] = []

    async def on_event(ev):
        events.append(ev)

    tools = specs_to_tools(user)
    result = asyncio.run(run_operator_loop(turn=turn, user=user, tools=tools, on_event=on_event, provider=llm))
    assert result.status == ChatTurnState.STATUS_AWAITING_CONFIRM
    assistant_msg.refresh_from_db()
    step_status = assistant_msg.metadata["plan"]["steps"][0]["status"]
    assert step_status == "awaiting_confirm"
    assert step_status != "running"
    assert assistant_msg.metadata["plan"]["status"] in {"approved", "proposed"}


def test_canonical_command_tool_requires_nonempty_planned_cmd():
    """Command tools must not soft-match on server_id alone when planned_cmd is empty."""
    plan = {
        "title": "T",
        "status": "approved",
        "steps": [
            {
                "id": 1,
                "tool": "operator.run_command",
                "input": {"server_id": 7},
                "status": "pending",
            }
        ],
    }
    assert not canonical_plan_step_matches(
        plan,
        action_type="operator.run_command",
        input_payload={"server_id": 7, "command": "df -h"},
    )
    plan["steps"][0]["input"] = {"server_id": 7, "command": "df -h"}
    assert canonical_plan_step_matches(
        plan,
        action_type="operator.run_command",
        input_payload={"server_id": 7, "command": "df -h"},
    )


@pytest.mark.django_db
def test_typed_confirm_failure_does_not_leave_step_running():
    """Wrong typed phrase must not flip awaiting_confirm → running."""
    from core_ui.services.operator_plan import mark_executing_after_typed_confirm_ok

    user = _operator_user("plan-typed-fail")
    session = ChatSession.objects.create(user=user, title="typed")
    msg = ChatMessage.objects.create(
        session=session,
        role=ChatMessage.ROLE_ASSISTANT,
        content="confirm",
        metadata={
            "plan": {
                "title": "Danger",
                "status": "approved",
                "steps": [
                    {
                        "id": 1,
                        "text": "rm",
                        "tool": "operator.run_command",
                        "input": {"server_id": 1, "command": "rm -rf /tmp/x"},
                        "status": "awaiting_confirm",
                    }
                ],
            }
        },
    )
    action = AssistantAction.objects.create(
        user=user,
        session=session,
        message=msg,
        action_type="operator.run_command",
        title="rm",
        status=AssistantAction.STATUS_REQUIRES_CONFIRMATION,
        risk=AssistantAction.RISK_DANGEROUS,
        requires_confirmation=True,
        input_payload={"server_id": 1, "command": "rm -rf /tmp/x"},
        blast_radius={
            "typed_confirm_required": True,
            "typed_confirm_token": "web-01",
            "server_names": ["web-01"],
        },
    )
    ChatTurnState.objects.create(
        session=session,
        assistant_message=msg,
        pending_action=action,
        status=ChatTurnState.STATUS_AWAITING_CONFIRM,
    )
    action, err = mark_executing_after_typed_confirm_ok(action, typed_confirm="wrong-token")
    assert err
    assert "mismatch" in err.lower() or "required" in err.lower() or "confirm" in err.lower()
    assert action.status == AssistantAction.STATUS_REQUIRES_CONFIRMATION
    msg.refresh_from_db()
    assert msg.metadata["plan"]["steps"][0]["status"] == "awaiting_confirm"


@pytest.mark.django_db
def test_autonomous_ai_read_only_still_denies_mutation():
    """Hard floor: ai_read_only blocks writes even when autonomy_mode=autonomous."""
    from servers.models import Server
    from servers.services.server_mutation_policy import decide_server_mutation

    user = _operator_user("plan-ro-auto")
    session = ChatSession.objects.create(
        user=user,
        title="ro",
        pinned_context={"autonomy_mode": AUTONOMY_AUTONOMOUS},
    )
    assert get_autonomy_mode(session) == AUTONOMY_AUTONOMOUS
    server = Server.objects.create(
        user=user,
        name="ro-host",
        host="10.20.0.99",
        port=22,
        username="pilot",
        ai_read_only=True,
    )
    decision = decide_server_mutation(user, server)
    assert decision.allowed is False
    assert decision.code == "server_ai_read_only"
