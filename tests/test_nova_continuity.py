from __future__ import annotations

import json
from typing import Any
from unittest.mock import patch

import pytest

from servers.services.terminal_ai.agent.loop import AgentContext, run_agent_loop
from servers.services.terminal_ai.agent.tools import ServerTarget, default_tool_set
from servers.services.terminal_ai.nova_conversation import (
    NovaConversationState,
    is_live_nova_followup,
    persist_nova_result,
    should_continue_nova,
)


class ScriptedLLM:
    def __init__(self, steps: list[dict]):
        self.steps = steps
        self.call_count = 0
        self.system_prompts: list[str] = []
        self.user_prompts: list[str] = []

    async def stream_chat(
        self,
        prompt: str,
        *,
        model: str = "auto",
        purpose: str = "",
        system_prompt: str | None = None,
        json_mode: bool = False,
        **_: Any,
    ):
        self.user_prompts.append(prompt)
        if system_prompt:
            self.system_prompts.append(system_prompt)
        idx = self.call_count
        self.call_count += 1
        if idx >= len(self.steps):
            yield json.dumps({"thinking": "", "tool": "done", "args": {}, "final_text": "fallback"})
            return
        yield json.dumps(self.steps[idx])


@pytest.fixture
def patch_llm():
    def _install(steps: list[dict]) -> ScriptedLLM:
        scripted = ScriptedLLM(steps)

        class FakeProvider:
            stream_chat = scripted.stream_chat

        patcher = patch("app.core.llm.LLMProvider", FakeProvider)
        patcher.start()
        return scripted

    yield _install
    patch.stopall()


def _primary() -> ServerTarget:
    return ServerTarget(name="primary", server_id=1, display_name="srv", is_primary=True)


def test_live_followup_only_for_running_nova():
    assert is_live_nova_followup(requested_mode="agent", running=True) is True
    assert is_live_nova_followup(requested_mode="agent", running=False) is False
    assert is_live_nova_followup(requested_mode="fast", running=True) is False


def test_persist_keeps_pending_interjections():
    conv = NovaConversationState()
    conv.enqueue_interjection("нет, лучше проверь nginx")
    persist_nova_result(
        conv,
        todos=[{"id": "1", "content": "check nginx", "status": "in_progress"}],
        history=[{"role": "tool_result", "content": "ok"}],
        final_text="частично",
    )
    assert conv.running is False
    assert conv.todos[0]["content"] == "check nginx"
    assert conv.pending_user_messages == ["нет, лучше проверь nginx"]
    assert should_continue_nova(conv) is True


@pytest.mark.asyncio
async def test_seed_todos_and_continuation_prompt(patch_llm):
    scripted = patch_llm(
        [
            {
                "thinking": "adapt",
                "tool": "done",
                "args": {},
                "final_text": "Переключил цель на nginx.",
            }
        ]
    )
    events: list[dict] = []

    async def emit(ev):
        events.append(ev)

    ctx = AgentContext(
        user_message="нет, лучше проверь nginx",
        primary=_primary(),
        emit=emit,
        seed_todos=[{"id": "1", "content": "проверить disk", "status": "in_progress"}],
        seed_history=[{"role": "tool_result", "content": "df showed 80%"}],
        continuation=True,
        max_iterations=3,
    )
    result = await run_agent_loop(ctx, default_tool_set())
    assert result.final_text == "Переключил цель на nginx."
    assert any(e["type"] == "agent_todo_update" for e in events)
    assert "continuation of the same Nova session" in scripted.system_prompts[0]
    assert "проверить disk" in str(events)


@pytest.mark.asyncio
async def test_pending_followup_is_user_interjection(patch_llm):
    scripted = patch_llm(
        [
            {
                "thinking": "ack",
                "tool": "done",
                "args": {},
                "final_text": "Принял уточнение.",
            }
        ]
    )
    pending = ["нет, лучше проверь nginx"]
    ctx = AgentContext(
        user_message="посмотри диск",
        primary=_primary(),
        pending_user_messages=pending,
        max_iterations=3,
    )
    await run_agent_loop(ctx, default_tool_set())
    assert pending == []
    assert "User interjection" in scripted.user_prompts[0]
    assert "проверь nginx" in scripted.user_prompts[0]


@pytest.mark.asyncio
async def test_primary_shell_uses_hidden_pty_callback(patch_llm):
    patch_llm(
        [
            {
                "thinking": "run",
                "tool": "shell",
                "args": {"cmd": "pwd"},
                "final_text": "",
            },
            {
                "thinking": "done",
                "tool": "done",
                "args": {},
                "final_text": "cwd kept",
            },
        ]
    )
    calls: list[tuple[str, int]] = []

    async def run_primary(cmd: str, timeout: int = 30):
        calls.append((cmd, timeout))
        return 0, "/opt/app\n"

    conn_calls: list[str] = []

    class FakeConn:
        async def run(self, cmd: str, **_: Any):
            conn_calls.append(cmd)

            class Result:
                stdout = ""
                stderr = ""
                exit_status = 0

            return Result()

    ctx = AgentContext(
        user_message="pwd",
        primary=ServerTarget(
            name="primary",
            server_id=1,
            is_primary=True,
            ssh_conn=FakeConn(),
        ),
        run_primary_shell=run_primary,
        primary_cwd="/opt/app",
        max_iterations=5,
    )
    result = await run_agent_loop(ctx, default_tool_set())
    assert result.final_text == "cwd kept"
    assert calls == [("pwd", 30)]
    assert conn_calls == []
