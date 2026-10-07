"""Operator multi-step continuation for SSH/log audit goals."""

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


def test_user_message_needs_ssh_actions_detects_audit_prompts():
    assert user_message_needs_ssh_actions("Проведи аудит сервера, проверь логи на ошибки @prom-01")
    assert user_message_needs_ssh_actions("Подключись и проверь логи")
    assert not user_message_needs_ssh_actions("Список серверов")


def test_messages_only_inventory_so_far():
    messages = [
        {
            "role": "assistant",
            "content": [{"type": "tool_use", "id": "1", "name": "operator_resolve_server", "input": {}}],
        },
        {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "1", "content": "{}"}]},
    ]
    assert messages_only_inventory_so_far(messages) is True
    messages[0]["content"].append(
        {"type": "tool_use", "id": "2", "name": "operator_read_command", "input": {"command": "df"}}
    )
    assert messages_only_inventory_so_far(messages) is False


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
