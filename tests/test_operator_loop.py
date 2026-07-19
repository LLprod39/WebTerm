"""Tests for Operator tool-calling loop (mocked LLM)."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from django.contrib.auth.models import User

from app.assistant_actions import AssistantActionSpec, get_action_spec, register_action
from app.core.llm_tools import normalise_tool_name
from core_ui.models import AssistantAction, ChatSession, ChatTurnState, UserAppPermission
from core_ui.services.assistant_chat import cancel_action, execute_action
from core_ui.services.operator_loop import handle_operator_message, resume_after_action
from core_ui.services.operator_tools import specs_to_tools


def _grant(user: User, *features: str) -> None:
    for feature in features:
        UserAppPermission.objects.update_or_create(
            user=user, feature=feature, defaults={"allowed": True}
        )


def _ensure_test_tools() -> None:
    if get_action_spec("operator.test_read") is None:
        register_action(
            AssistantActionSpec(
                action_type="operator.test_read",
                label="Test read",
                description="Read-only test tool",
                required_feature="servers",
                risk="read",
                input_schema={"type": "object", "properties": {"q": {"type": "string"}}},
                handler=lambda ctx: {"ok": True, "echo": ctx.input_payload, "count": 1},
            )
        )
    if get_action_spec("operator.test_mutate") is None:
        register_action(
            AssistantActionSpec(
                action_type="operator.test_mutate",
                label="Test mutate",
                description="Mutating test tool",
                required_feature="servers",
                risk="mutating",
                requires_confirmation=True,
                input_schema={
                    "type": "object",
                    "properties": {"cmd": {"type": "string"}},
                    "required": ["cmd"],
                },
                handler=lambda ctx: {"ok": True, "mutated": True, "cmd": ctx.input_payload.get("cmd")},
            )
        )


class ScriptedToolsLLM:
    """Emits scripted stream_chat_tools event sequences per iteration."""

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


@pytest.fixture
def operator_user(db):
    _ensure_test_tools()
    user = User.objects.create_user(username="op-user", password="x")
    _grant(user, "orchestrator", "servers", "agents")
    return user


@pytest.mark.django_db(transaction=True)
def test_operator_loop_read_tools_then_answer(operator_user):
    session = ChatSession.objects.create(user=operator_user, title="t")
    llm = ScriptedToolsLLM(
        [
            [
                {"type": "text_delta", "text": "Looking…"},
                {
                    "type": "tool_call",
                    "id": "call_1",
                    "name": "operator_test_read",
                    "arguments": {"q": "fleet"},
                },
                {"type": "done", "usage": {"input_tokens": 10, "output_tokens": 5}, "stop_reason": "tool_use"},
            ],
            [
                {"type": "text_delta", "text": " Fleet is fine."},
                {"type": "done", "usage": {"input_tokens": 20, "output_tokens": 8}, "stop_reason": "end_turn"},
            ],
        ]
    )
    events: list[dict] = []

    async def on_event(ev):
        events.append(ev)

    result = asyncio.run(
        handle_operator_message(
            session, operator_user, "что с флотом?", on_event=on_event, provider=llm
        )
    )

    assert result.status == ChatTurnState.STATUS_DONE
    assert "Looking" in result.assistant_message.content
    assert "Fleet is fine" in result.assistant_message.content
    assert any(e.get("type") == "tool_started" for e in events)
    assert any(e.get("type") == "tool_result" for e in events)
    assert any(e.get("type") == "token" for e in events)
    assert llm.call_count == 2


@pytest.mark.django_db(transaction=True)
def test_operator_loop_parks_mutate_and_resumes(operator_user):
    session = ChatSession.objects.create(user=operator_user, title="t")
    llm = ScriptedToolsLLM(
        [
            [
                {"type": "text_delta", "text": "Need to run a command."},
                {
                    "type": "tool_call",
                    "id": "call_m",
                    "name": "operator_test_mutate",
                    "arguments": {"cmd": "df -h"},
                },
                {"type": "done", "usage": {}, "stop_reason": "tool_use"},
            ],
            [
                {"type": "text_delta", "text": " Done after confirm."},
                {"type": "done", "usage": {}, "stop_reason": "end_turn"},
            ],
        ]
    )

    result = asyncio.run(handle_operator_message(session, operator_user, "выполни df", provider=llm))
    assert result.status == ChatTurnState.STATUS_AWAITING_CONFIRM
    assert result.actions
    action = result.actions[0]
    assert action.status == AssistantAction.STATUS_REQUIRES_CONFIRMATION
    assert action.action_type == "operator.test_mutate"

    action = execute_action(action, confirmed=True)
    assert action.status == AssistantAction.STATUS_COMPLETED

    resumed = asyncio.run(resume_after_action(action=action, provider=llm, cancelled=False))
    assert resumed is not None
    assert resumed.status == ChatTurnState.STATUS_DONE
    assert "Done after confirm" in resumed.assistant_message.content


@pytest.mark.django_db(transaction=True)
def test_operator_loop_cancel_resumes_with_rejection(operator_user):
    session = ChatSession.objects.create(user=operator_user, title="t")
    llm = ScriptedToolsLLM(
        [
            [
                {
                    "type": "tool_call",
                    "id": "call_c",
                    "name": "operator_test_mutate",
                    "arguments": {"cmd": "rm -rf /"},
                },
                {"type": "done", "usage": {}, "stop_reason": "tool_use"},
            ],
            [
                {"type": "text_delta", "text": "Understood, cancelled."},
                {"type": "done", "usage": {}, "stop_reason": "end_turn"},
            ],
        ]
    )
    result = asyncio.run(handle_operator_message(session, operator_user, "удали всё", provider=llm))
    action = result.actions[0]
    action = cancel_action(action)
    resumed = asyncio.run(resume_after_action(action=action, provider=llm, cancelled=True))
    assert resumed is not None
    assert resumed.status == ChatTurnState.STATUS_DONE
    assert "cancelled" in resumed.assistant_message.content.lower() or "Understood" in resumed.assistant_message.content


@pytest.mark.django_db
def test_specs_to_tools_normalises_names(operator_user):
    tools = specs_to_tools(operator_user)
    names = {t["name"] for t in tools}
    assert "operator_test_read" in names
    assert "operator_test_mutate" in names
    assert normalise_tool_name("agents.list") == "agents_list"


@pytest.mark.django_db(transaction=True)
def test_operator_loop_auto_executes_approved_plan_step(operator_user):
    """P1.7: a non-destructive step of an APPROVED plan runs without re-confirming."""
    from core_ui.models import ChatMessage
    from core_ui.services.operator_loop import run_operator_loop

    session = ChatSession.objects.create(user=operator_user, title="plan")
    user_msg = ChatMessage.objects.create(
        session=session, role=ChatMessage.ROLE_USER, content="выполни план"
    )
    assistant_msg = ChatMessage.objects.create(
        session=session,
        role=ChatMessage.ROLE_ASSISTANT,
        content="",
        metadata={
            "plan": {
                "title": "Проверка",
                "status": "approved",
                "steps": [
                    {"id": 1, "text": "run mutate", "tool": "operator_test_mutate", "status": "pending"}
                ],
            }
        },
    )
    turn = ChatTurnState.objects.create(
        session=session,
        user_message=user_msg,
        assistant_message=assistant_msg,
        status=ChatTurnState.STATUS_RUNNING,
        llm_messages=[{"role": "user", "content": "выполни план"}],
    )
    llm = ScriptedToolsLLM(
        [
            [
                {
                    "type": "tool_call",
                    "id": "call_step",
                    "name": "operator_test_mutate",
                    "arguments": {"cmd": "df -h"},
                },
                {"type": "done", "usage": {}, "stop_reason": "tool_use"},
            ],
            [
                {"type": "text_delta", "text": "Шаг выполнен."},
                {"type": "done", "usage": {}, "stop_reason": "end_turn"},
            ],
        ]
    )
    events: list[dict] = []

    async def on_event(ev):
        events.append(ev)

    tools = specs_to_tools(operator_user)
    result = asyncio.run(
        run_operator_loop(turn=turn, user=operator_user, tools=tools, on_event=on_event, provider=llm)
    )

    assert result.status == ChatTurnState.STATUS_DONE
    action = AssistantAction.objects.filter(
        session=session, action_type="operator.test_mutate"
    ).first()
    assert action is not None
    # Auto-executed within the approved plan — NOT parked awaiting confirmation.
    assert action.status == AssistantAction.STATUS_COMPLETED
    assert any(e.get("type") == "action_update" for e in events)
    assert any(e.get("type") == "plan_update" for e in events)
    assert not any(e.get("type") == "confirm_required" for e in events)
    assert "Шаг выполнен" in (result.assistant_message.content or "")
