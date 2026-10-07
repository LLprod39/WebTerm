"""Operator multi-step continuation for SSH/log audit and what's-running goals."""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import patch

import pytest
from django.contrib.auth.models import User

from app.assistant_actions import AssistantActionSpec, get_action_spec, register_action
from core_ui.models import ChatSession, ChatTurnState
from core_ui.services.operator_loop import handle_operator_message
from core_ui.services.operator_loop_prompt import (
    messages_only_inventory_so_far,
    should_continue_after_inventory_only,
    user_message_needs_ssh_actions,
)


class ScriptedToolsLLM:
    def __init__(self, iterations: list[list[dict[str, Any]]]):
        self.iterations = iterations
        self.call_count = 0
        self.seen_messages: list[Any] = []

    async def stream_chat_tools(self, messages, tools, **kwargs):
        self.seen_messages.append(messages)
        idx = self.call_count
        self.call_count += 1
        if idx >= len(self.iterations):
            yield {"type": "text_delta", "text": "done"}
            yield {"type": "done", "usage": {}, "stop_reason": "end_turn"}
            return
        for event in self.iterations[idx]:
            yield event


def _ensure_tools() -> None:
    if get_action_spec("operator.test_read") is None:
        register_action(
            AssistantActionSpec(
                action_type="operator.test_read",
                label="Test read",
                description="Read-only test tool",
                required_feature="servers",
                risk="read",
                input_schema={"type": "object", "properties": {"q": {"type": "string"}}},
                handler=lambda ctx: {"ok": True, "echo": ctx.input_payload},
            )
        )
    if get_action_spec("operator.resolve_server") is None:
        register_action(
            AssistantActionSpec(
                action_type="operator.resolve_server",
                label="Resolve server",
                description="Resolve",
                required_feature="servers",
                risk="read",
                input_schema={"type": "object", "properties": {"q": {"type": "string"}}},
                handler=lambda ctx: {"ok": True, "found": True, "server_id": 7, "name": "prom-01"},
            )
        )
    if get_action_spec("operator.read_command") is None:
        register_action(
            AssistantActionSpec(
                action_type="operator.read_command",
                label="Read command",
                description="Bounded read-only SSH",
                required_feature="servers",
                risk="read",
                input_schema={
                    "type": "object",
                    "properties": {
                        "server_id": {"type": "integer"},
                        "command": {"type": "string"},
                    },
                },
                handler=lambda ctx: {
                    "ok": True,
                    "exit_code": 0,
                    "output": "nginx.service running\ngrafana running",
                    "read_only": True,
                },
            )
        )


def test_user_message_needs_ssh_actions_detects_audit_prompts():
    assert user_message_needs_ssh_actions("Проведи аудит сервера, проверь логи на ошибки @prom-01")
    assert user_message_needs_ssh_actions("Подключись и проверь логи")
    assert user_message_needs_ssh_actions("@grafana-01 проверь что на этом сервере крутится")
    assert user_message_needs_ssh_actions("проверь что на сервере крутится")
    assert user_message_needs_ssh_actions("@host-1 what's running")
    assert user_message_needs_ssh_actions("глянь что с @grafana-01")
    assert not user_message_needs_ssh_actions("Список серверов")
    assert not user_message_needs_ssh_actions("Привет")
    assert not user_message_needs_ssh_actions("Что умеешь?")
    # Metrics-only must not force SSH follow-through.
    assert not user_message_needs_ssh_actions("@grafana-01 проверь метрики")


def test_messages_only_inventory_so_far():
    messages = [
        {
            "role": "assistant",
            "content": [{"type": "tool_use", "id": "1", "name": "operator_resolve_server", "input": {}}],
        },
        {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "1", "content": "{}"}]},
    ]
    assert messages_only_inventory_so_far(messages) is True
    assert should_continue_after_inventory_only(
        "@grafana-01 проверь что на этом сервере крутится", messages
    )
    messages[0]["content"].append(
        {"type": "tool_use", "id": "2", "name": "operator_read_command", "input": {"command": "df"}}
    )
    assert messages_only_inventory_so_far(messages) is False
    assert not should_continue_after_inventory_only(
        "@grafana-01 проверь что на этом сервере крутится", messages
    )


@pytest.mark.django_db(transaction=True)
def test_operator_nudges_after_inventory_only_stop_on_log_audit():
    _ensure_tools()
    user = User.objects.create_user(username="op-cont-user", password="x")
    from core_ui.views.access_views import _apply_access_profile

    _apply_access_profile(user, "pilot_operator")
    session = ChatSession.objects.create(user=user, title="audit")

    llm = ScriptedToolsLLM(
        [
            [
                {
                    "type": "tool_call",
                    "id": "c1",
                    "name": "operator_resolve_server",
                    "arguments": {"q": "prom-01"},
                },
                {"type": "done", "usage": {}, "stop_reason": "tool_use"},
            ],
            [
                {"type": "text_delta", "text": "Сервер найден, на этом всё."},
                {"type": "done", "usage": {}, "stop_reason": "end_turn"},
            ],
            [
                {
                    "type": "tool_call",
                    "id": "c2",
                    "name": "operator_test_read",
                    "arguments": {"q": "journalctl"},
                },
                {"type": "done", "usage": {}, "stop_reason": "tool_use"},
            ],
            [
                {"type": "text_delta", "text": "Итоговый отчёт: в journalctl ошибок нет."},
                {"type": "done", "usage": {}, "stop_reason": "end_turn"},
            ],
        ]
    )

    def fake_execute_tool(**kwargs):
        action = kwargs.get("action_type") or ""
        if "resolve" in action:
            return {"ok": True, "result": {"found": True, "server_id": 7, "name": "prom-01"}}
        return {"ok": True, "result": {"ok": True, "output": "no errors", "exit_code": 0}}

    with patch("core_ui.services.operator_loop_tool_cycle.execute_tool", side_effect=fake_execute_tool):
        result = asyncio.run(
            handle_operator_message(
                session,
                user,
                "Проведи аудит сервера, проверь логи на ошибки @prom-01",
                provider=llm,
            )
        )

    assert result.status == ChatTurnState.STATUS_DONE
    # resolve → premature text → nudge → read tool → final report
    assert llm.call_count >= 3
    assert "Итоговый отчёт" in (result.assistant_message.content or "")
    assert any("operator.read_command" in str(batch) for batch in llm.seen_messages)


@pytest.mark.django_db(transaction=True)
def test_operator_continues_whats_running_after_resolve_to_ssh_summary():
    """@mention + «что крутится» must reach SSH read commands and a final summary."""
    _ensure_tools()
    user = User.objects.create_user(username="op-running-user", password="x")
    from core_ui.views.access_views import _apply_access_profile

    _apply_access_profile(user, "pilot_operator")
    session = ChatSession.objects.create(user=user, title="whats-running")
    events: list[dict[str, Any]] = []

    async def on_event(event):
        events.append(event)

    llm = ScriptedToolsLLM(
        [
            [
                {
                    "type": "tool_call",
                    "id": "r1",
                    "name": "operator_resolve_server",
                    "arguments": {"q": "grafana-01"},
                },
                {"type": "done", "usage": {}, "stop_reason": "tool_use"},
            ],
            [
                {
                    "type": "text_delta",
                    "text": "Сервер grafana-01 найден (id=18), статус healthy. Терминал: /servers/18/terminal",
                },
                {"type": "done", "usage": {}, "stop_reason": "end_turn"},
            ],
            [
                {
                    "type": "tool_call",
                    "id": "r2",
                    "name": "operator_read_command",
                    "arguments": {
                        "server_id": 18,
                        "command": "systemctl list-units --type=service --state=running",
                    },
                },
                {"type": "done", "usage": {}, "stop_reason": "tool_use"},
            ],
            [
                {
                    "type": "text_delta",
                    "text": "Итог: на grafana-01 крутятся nginx и grafana; слушатели и top-процессы собраны.",
                },
                {"type": "done", "usage": {}, "stop_reason": "end_turn"},
            ],
        ]
    )

    def fake_execute_tool(**kwargs):
        action = kwargs.get("action_type") or ""
        if "resolve" in action:
            return {
                "ok": True,
                "result": {"found": True, "server_id": 18, "name": "grafana-01", "status": "healthy"},
            }
        return {
            "ok": True,
            "result": {
                "ok": True,
                "exit_code": 0,
                "output": "nginx.service loaded active running\ngrafana-server.service loaded active running",
                "read_only": True,
            },
        }

    with patch("core_ui.services.operator_loop_tool_cycle.execute_tool", side_effect=fake_execute_tool):
        result = asyncio.run(
            handle_operator_message(
                session,
                user,
                "@grafana-01 проверь что на этом сервере крутится",
                provider=llm,
                on_event=on_event,
            )
        )

    assert result.status == ChatTurnState.STATUS_DONE
    assert llm.call_count >= 3
    assert "Итог" in (result.assistant_message.content or "")
    # Nudge / progress path must mention read_command follow-through.
    assert any("operator.read_command" in str(batch) or "systemctl" in str(batch) for batch in llm.seen_messages)
    progress_msgs = [
        e.get("message")
        for e in events
        if e.get("type") == "thinking" and e.get("phase") in {"progress", "continue"}
    ]
    assert progress_msgs, "expected streamed progress/continue events for UI"


@pytest.mark.django_db(transaction=True)
def test_operator_greeting_stays_single_step():
    """Chit-chat must not enter the SSH continuation loop."""
    _ensure_tools()
    user = User.objects.create_user(username="op-hi-user", password="x")
    from core_ui.views.access_views import _apply_access_profile

    _apply_access_profile(user, "pilot_operator")
    session = ChatSession.objects.create(user=user, title="hi")

    llm = ScriptedToolsLLM(
        [
            [
                {"type": "text_delta", "text": "Привет! Чем помочь по флоту?"},
                {"type": "done", "usage": {}, "stop_reason": "end_turn"},
            ],
        ]
    )

    result = asyncio.run(
        handle_operator_message(
            session,
            user,
            "Привет",
            provider=llm,
        )
    )

    assert result.status == ChatTurnState.STATUS_DONE
    assert llm.call_count == 1
    assert "Привет" in (result.assistant_message.content or "")


@pytest.mark.django_db(transaction=True)
def test_operator_self_check_continues_glance_host_without_keyword_match():
    """«глянь что с @host» must reach SSH via model-driven self-check (not only KW)."""
    _ensure_tools()
    user = User.objects.create_user(username="op-glance-user", password="x")
    from core_ui.views.access_views import _apply_access_profile

    _apply_access_profile(user, "pilot_operator")
    session = ChatSession.objects.create(user=user, title="glance")
    events: list[dict[str, Any]] = []

    async def on_event(event):
        events.append(event)

    llm = ScriptedToolsLLM(
        [
            [
                {
                    "type": "tool_call",
                    "id": "g1",
                    "name": "operator_resolve_server",
                    "arguments": {"q": "grafana-01"},
                },
                {"type": "done", "usage": {}, "stop_reason": "tool_use"},
            ],
            [
                {"type": "text_delta", "text": "Сервер найден."},
                {"type": "done", "usage": {}, "stop_reason": "end_turn"},
            ],
            [
                {
                    "type": "tool_call",
                    "id": "g2",
                    "name": "operator_read_command",
                    "arguments": {"server_id": 18, "command": "systemctl list-units --type=service --state=running"},
                },
                {"type": "done", "usage": {}, "stop_reason": "tool_use"},
            ],
            [
                {
                    "type": "tool_call",
                    "id": "g3",
                    "name": "operator_finish_report",
                    "arguments": {"summary": "Итог: на grafana-01 крутятся nginx и grafana."},
                },
                {"type": "done", "usage": {}, "stop_reason": "tool_use"},
            ],
        ]
    )

    def fake_execute_tool(**kwargs):
        action = kwargs.get("action_type") or ""
        if "resolve" in action:
            return {"ok": True, "result": {"found": True, "server_id": 18, "name": "grafana-01"}}
        return {
            "ok": True,
            "result": {
                "ok": True,
                "exit_code": 0,
                "output": "nginx.service running\ngrafana-server.service running",
                "read_only": True,
            },
        }

    with patch("core_ui.services.operator_loop_tool_cycle.execute_tool", side_effect=fake_execute_tool):
        result = asyncio.run(
            handle_operator_message(
                session,
                user,
                "глянь что с @grafana-01",
                provider=llm,
                on_event=on_event,
            )
        )

    assert result.status == ChatTurnState.STATUS_DONE
    assert llm.call_count >= 3
    assert "Итог" in (result.assistant_message.content or "")
    assert any(
        e.get("type") == "thinking" and e.get("phase") in {"progress", "continue"} for e in events
    )
    # Self-check nudge must appear in LLM history before SSH follow-through.
    assert any("Self-check" in str(batch) or "self-check" in str(batch).lower() for batch in llm.seen_messages)


@pytest.mark.django_db(transaction=True)
def test_operator_provider_error_ends_stream_failed():
    _ensure_tools()
    user = User.objects.create_user(username="op-err-user", password="x")
    from core_ui.views.access_views import _apply_access_profile

    _apply_access_profile(user, "pilot_operator")
    session = ChatSession.objects.create(user=user, title="err")

    class FailingLLM:
        call_count = 0

        async def stream_chat_tools(self, messages, tools, **kwargs):
            self.call_count += 1
            yield {"type": "error", "message": "provider_auth_required: re-auth Antigravity"}
            yield {"type": "done", "usage": {}, "stop_reason": "error"}

    llm = FailingLLM()
    result = asyncio.run(handle_operator_message(session, user, "Привет", provider=llm))
    assert result.status == ChatTurnState.STATUS_FAILED
    assert llm.call_count == 1
    assert "Ошибка LLM" in (result.assistant_message.content or "") or "provider_auth" in (
        result.turn_state.error or ""
    )


@pytest.mark.django_db(transaction=True)
def test_operator_step_cap_produces_limit_report():
    _ensure_tools()
    user = User.objects.create_user(username="op-cap-user", password="x")
    from core_ui.views.access_views import _apply_access_profile

    _apply_access_profile(user, "pilot_operator")
    session = ChatSession.objects.create(user=user, title="cap")

    # Force step limit: every call returns another read tool until cap.
    class CapLLM:
        def __init__(self):
            self.call_count = 0

        async def stream_chat_tools(self, messages, tools, **kwargs):
            self.call_count += 1
            # After many iterations the loop injects final-report nudge (no tools).
            if any(
                isinstance(m.get("content"), str) and "лимит шагов" in m.get("content", "")
                for m in messages
                if isinstance(m, dict)
            ):
                yield {"type": "text_delta", "text": "Итоговый отчёт по лимиту шагов."}
                yield {"type": "done", "usage": {}, "stop_reason": "end_turn"}
                return
            yield {
                "type": "tool_call",
                "id": f"c{self.call_count}",
                "name": "operator_test_read",
                "arguments": {"q": "x"},
            }
            yield {"type": "done", "usage": {}, "stop_reason": "tool_use"}

    llm = CapLLM()

    with patch(
        "core_ui.services.operator_loop_tool_cycle.execute_tool",
        return_value={"ok": True, "result": {"ok": True}},
    ):
        with patch("core_ui.services.operator_loop.MAX_ITERATIONS", 2):
            result = asyncio.run(
                handle_operator_message(session, user, "Список серверов", provider=llm)
            )

    assert result.status == ChatTurnState.STATUS_LIMIT
    assert "Итоговый отчёт" in (result.assistant_message.content or "")
