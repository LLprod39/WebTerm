"""Fire-scenario integration + pilot policy + plan progress tests."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from django.contrib.auth.models import User

from app.assistant_actions import AssistantActionSpec, get_action_spec, register_action
from core_ui.models import AssistantAction, ChatMessage, ChatSession, ChatTurnState, UserAppPermission
from core_ui.services.assistant_chat import execute_action
from core_ui.services.operator_loop import handle_operator_message
from core_ui.services.operator_plan import (
    advance_plan_on_action,
    apply_plan_progress,
    approved_plan_step_matches,
    mark_plan_approved,
)
from core_ui.services.operator_policy import filter_tools_for_policy, is_pilot_restricted_operator
from core_ui.services.operator_tools import execute_tool, specs_to_tools
from core_ui.views.access_views import _apply_access_profile
from servers.operator.mutate_tools import register_operator_mutate_tools
from servers.operator.tools import register_operator_tools


def _grant(user: User, *features: str) -> None:
    for feature in features:
        UserAppPermission.objects.update_or_create(user=user, feature=feature, defaults={"allowed": True})


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


@pytest.mark.django_db
def test_pilot_policy_exposes_only_read_tools_without_exact_operator_profile(monkeypatch):
    monkeypatch.setenv("PILOT_RESTRICTED_MODE", "true")
    pilot = User.objects.create_user(username="pilot1", password="x")
    _grant(pilot, "orchestrator", "servers", "agents")
    assert is_pilot_restricted_operator(pilot) is True

    staff = User.objects.create_user(username="staff1", password="x", is_staff=True)
    assert is_pilot_restricted_operator(staff) is True

    register_operator_tools()
    register_operator_mutate_tools()
    tools = specs_to_tools(pilot)
    # Studio tools should not appear for pilot
    assert not any(str(t.get("action_type") or "").startswith("studio.") for t in tools)
    # Mutates are not listed at all for ordinary pilot/staff users.
    mutates = [t for t in tools if t.get("risk") != "read"]
    assert mutates == []

    # filter is idempotent
    assert len(filter_tools_for_policy(pilot, tools)) == len(tools)

    operator = User.objects.create_user(username="pilot-operator-policy", password="x")
    _apply_access_profile(operator, "pilot_operator")
    assert is_pilot_restricted_operator(operator) is False
    assert any(t.get("risk") != "read" for t in specs_to_tools(operator))


@pytest.mark.django_db
def test_direct_mutating_tool_and_pending_action_recheck_pilot_operator_authority(monkeypatch):
    monkeypatch.setenv("PILOT_RESTRICTED_MODE", "true")
    calls: list[str] = []
    action_type = "test.pilot_mutation_boundary"
    if get_action_spec(action_type) is None:
        register_action(
            AssistantActionSpec(
                action_type=action_type,
                label="Pilot mutation boundary",
                description="Test-only mutation boundary",
                risk=AssistantAction.RISK_MUTATING,
                requires_confirmation=True,
                required_feature="servers",
                handler=lambda ctx: calls.append(str(ctx.user.pk)) or {"ok": True},
            )
        )
    pilot = User.objects.create_user(username="pilot-direct-mutate", password="x")
    staff = User.objects.create_user(username="staff-direct-mutate", password="x", is_staff=True)
    operator = User.objects.create_user(username="pilot-operator-direct-mutate", password="x")
    _apply_access_profile(operator, "pilot_operator")

    for user in (pilot, staff):
        denied = execute_tool(user=user, action_type=action_type, arguments={})
        assert denied["code"] == "automation_required"
        session = ChatSession.objects.create(user=user, title="denied mutation")
        pending = AssistantAction.objects.create(
            user=user,
            session=session,
            action_type=action_type,
            title="Denied mutation",
            status=AssistantAction.STATUS_REQUIRES_CONFIRMATION,
            risk=AssistantAction.RISK_MUTATING,
            required_feature="servers",
            requires_confirmation=True,
        )
        result = execute_action(pending, confirmed=True)
        assert result.status == AssistantAction.STATUS_FAILED
        assert "pilot_operator" in result.error

    allowed = execute_tool(user=operator, action_type=action_type, arguments={})
    assert allowed["ok"] is True
    assert calls == [str(operator.pk)]


@pytest.mark.django_db
def test_plan_advance_helpers():
    plan = {
        "title": "Fire",
        "steps": [
            {"id": 1, "text": "Check fleet", "tool": "operator.fleet_status", "status": "pending"},
            {"id": 2, "text": "Run df", "tool": "operator.run_command", "status": "pending"},
        ],
    }
    plan = mark_plan_approved(plan)
    assert plan["status"] == "approved"
    plan = advance_plan_on_action(plan, action_type="operator.fleet_status", ok=True)
    assert plan["steps"][0]["status"] == "done"
    assert plan["status"] == "running"
    plan = advance_plan_on_action(plan, action_type="operator.run_command", ok=True)
    assert plan["steps"][1]["status"] == "done"
    assert plan["status"] == "completed"


@pytest.mark.django_db(transaction=True)
def test_fire_scenario_scripted_loop():
    """«Пожар» path: fleet_status → propose_plan → (park) with scripted LLM."""
    register_operator_tools()
    register_operator_mutate_tools()
    user = User.objects.create_user(username="fire-op", password="x")
    _grant(user, "orchestrator", "servers", "agents")
    session = ChatSession.objects.create(user=user, title="fire")

    # Ensure test read tool for fleet-like behavior exists
    if get_action_spec("operator.fleet_status") is None:
        register_action(
            AssistantActionSpec(
                action_type="operator.fleet_status",
                label="Fleet",
                description="Fleet",
                required_feature="servers",
                risk="read",
                handler=lambda ctx: {"count": 1, "worst": [{"name": "db-01", "status": "critical"}], "ok": True},
            )
        )

    llm = ScriptedToolsLLM(
        [
            [
                {"type": "text_delta", "text": "## Диагностика\nСмотрю флот…\n"},
                {
                    "type": "tool_call",
                    "id": "c1",
                    "name": "operator_fleet_status",
                    "arguments": {},
                },
                {"type": "done", "usage": {"input_tokens": 5, "output_tokens": 5}, "stop_reason": "tool_use"},
            ],
            [
                {"type": "text_delta", "text": "Худший db-01. Предлагаю план:\n"},
                {
                    "type": "tool_call",
                    "id": "c2",
                    "name": "operator_propose_plan",
                    "arguments": {
                        "title": "Пожар db-01",
                        "steps": [
                            {"text": "du WAL", "tool": "operator.run_command"},
                            {"text": "cleanup playbook", "tool": "operator.create_playbook"},
                        ],
                    },
                },
                {"type": "done", "usage": {}, "stop_reason": "tool_use"},
            ],
        ]
    )
    events: list[dict] = []

    async def on_event(ev):
        events.append(ev)

    result = asyncio.run(
        handle_operator_message(
            session,
            user,
            "Что с флотом? Почини самое горячее.",
            on_event=on_event,
            provider=llm,
        )
    )
    assert result.status == ChatTurnState.STATUS_AWAITING_CONFIRM
    assert result.actions
    assert result.actions[0].action_type == "operator.propose_plan"
    assert any(e.get("type") == "plan_update" for e in events)
    assert any(e.get("type") == "tool_started" for e in events)
    # Assistant has markdown diagnosis text
    assert result.assistant_message.content
    assert "флот" in result.assistant_message.content.lower() or "Диагностика" in result.assistant_message.content


@pytest.mark.django_db
def test_apply_plan_progress_on_message():
    user = User.objects.create_user(username="plan-msg", password="x")
    session = ChatSession.objects.create(user=user)
    msg = ChatMessage.objects.create(
        session=session,
        role="assistant",
        content="plan",
        metadata={
            "plan": {
                "title": "T",
                "status": "approved",
                "steps": [
                    {"id": 1, "text": "A", "tool": "operator.run_command", "status": "pending"},
                    {"id": 2, "text": "B", "tool": "operator.save_runbook", "status": "pending"},
                ],
            }
        },
    )
    plan = apply_plan_progress(
        message=msg,
        turn=None,
        action_type="operator.run_command",
        ok=True,
    )
    assert plan is not None
    msg.refresh_from_db()
    assert msg.metadata["plan"]["steps"][0]["status"] == "done"


def test_approved_plan_requires_exact_tool_and_payload():
    plan = {
        "title": "Deploy",
        "status": "approved",
        "steps": [
            {
                "id": 1,
                "text": "restart web",
                "tool": "operator.run_command",
                "input": {"server_id": 7, "command": "systemctl restart nginx"},
                "status": "pending",
            }
        ],
    }
    assert approved_plan_step_matches(
        plan,
        action_type="operator.run_command",
        input_payload={"server_id": 7, "command": "systemctl restart nginx"},
    )
    assert not approved_plan_step_matches(
        plan,
        action_type="operator.run_command",
        input_payload={"server_id": 8, "command": "systemctl restart nginx"},
    )
    assert not approved_plan_step_matches(
        plan,
        action_type="operator.run_fanout",
        input_payload={"server_ids": [7], "command": "systemctl restart nginx"},
    )
