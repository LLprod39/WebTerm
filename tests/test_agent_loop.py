"""Tests for the Terminal Agent ReAct loop.

The LLM is mocked with a fake ``stream_chat`` that emits scripted
:class:`AgentStep` JSON payloads one per iteration. This lets us
verify loop behaviour deterministically.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from unittest.mock import patch

import pytest

from servers.services.terminal_ai.agent.loop import (
    AgentContext,
    run_agent_loop,
)
from servers.services.terminal_ai.agent.prompts import build_system_prompt
from servers.services.terminal_ai.agent.tools import (
    ServerTarget,
    default_tool_set,
)

# ---------------------------------------------------------------------------
# Fake LLM — scripted step-by-step replies
# ---------------------------------------------------------------------------


class ScriptedLLM:
    """Records calls and returns pre-canned JSON step-responses."""

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
            # Out of script — emit a 'done' to halt the loop cleanly.
            yield json.dumps({"thinking": "", "tool": "done", "args": {}, "final_text": "fallback"})
            return
        yield json.dumps(self.steps[idx])


@pytest.fixture
def patch_llm():
    """Return a helper that installs a ScriptedLLM for one test."""

    def _install(steps: list[dict]) -> ScriptedLLM:
        scripted = ScriptedLLM(steps)

        class FakeProvider:
            def __init__(self):
                pass

            stream_chat = scripted.stream_chat

        patcher = patch("app.core.llm.LLMProvider", FakeProvider)
        patcher.start()
        return scripted

    yield _install
    patch.stopall()


# ---------------------------------------------------------------------------
# Fake SSH + helpers
# ---------------------------------------------------------------------------


@dataclass
class FakeRunResult:
    stdout: str = ""
    stderr: str = ""
    exit_status: int | None = 0


class FakeSSHConn:
    def __init__(self, default: FakeRunResult | None = None):
        self.default = default or FakeRunResult(stdout="", exit_status=0)
        self.calls: list[str] = []

    async def run(self, cmd: str, **_: Any) -> FakeRunResult:
        self.calls.append(cmd)
        return self.default


def _primary(ssh_conn: Any = None) -> ServerTarget:
    return ServerTarget(
        name="primary",
        server_id=1,
        display_name="srv-main",
        host="10.0.0.1",
        ssh_conn=ssh_conn or FakeSSHConn(),
        is_primary=True,
    )


# ---------------------------------------------------------------------------
# Loop behaviour
# ---------------------------------------------------------------------------


class TestAgentLoop:
    @pytest.mark.asyncio
    async def test_done_on_first_turn_stops_immediately(self, patch_llm):
        patch_llm(
            [
                {
                    "thinking": "trivial",
                    "tool": "done",
                    "args": {},
                    "final_text": "Nothing to do.",
                }
            ]
        )
        events: list[dict] = []

        async def emit(ev):
            events.append(ev)

        ctx = AgentContext(
            user_message="say hi",
            primary=_primary(),
            emit=emit,
            max_iterations=5,
        )
        result = await run_agent_loop(ctx, default_tool_set())
        assert result.final_text == "Nothing to do."
        assert result.iterations == 1
        assert result.tool_calls == 0
        assert result.stopped is False
        # agent_start + agent_done emitted
        event_types = [e["type"] for e in events]
        assert "agent_start" in event_types
        assert "agent_done" in event_types

    @pytest.mark.asyncio
    async def test_done_with_final_text_in_args_is_recovered(self, patch_llm):
        # Regression: weaker LLMs read the ``done`` tool schema from the
        # catalogue (which advertises ``final_text`` as an *arg*) and pack
        # the summary into ``args`` instead of the top-level ``final_text``
        # field the loop inspects. Previously this dropped the entire
        # final answer; the loop must now recover from either shape.
        patch_llm(
            [
                {
                    "thinking": "finish",
                    "tool": "done",
                    "args": {"final_text": "Готово: серверы живы."},
                    "final_text": "",
                }
            ]
        )
        ctx = AgentContext(
            user_message="check",
            primary=_primary(),
            max_iterations=5,
        )
        result = await run_agent_loop(ctx, default_tool_set())
        assert result.final_text == "Готово: серверы живы."
        assert result.stopped is False

    @pytest.mark.asyncio
    async def test_done_without_any_final_text_falls_back(self, patch_llm):
        # If the model emits ``done`` with an empty summary in every
        # possible location, the loop must still produce a non-empty
        # ``final_text`` so the UI doesn't end with silent tool walls.
        patch_llm(
            [
                {
                    "thinking": "",
                    "tool": "done",
                    "args": {},
                    "final_text": "",
                }
            ]
        )
        ctx = AgentContext(
            user_message="check",
            primary=_primary(),
            max_iterations=5,
        )
        result = await run_agent_loop(ctx, default_tool_set())
        assert result.final_text  # never empty
        assert result.stopped is False

    @pytest.mark.asyncio
    async def test_transient_retryable_llm_error_recovers(self):
        class FlakyProvider:
            call_count = 0

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
                if FlakyProvider.call_count == 0:
                    FlakyProvider.call_count += 1
                    yield "Error: 503 upstream unavailable"
                    return
                FlakyProvider.call_count += 1
                yield json.dumps(
                    {
                        "thinking": "finish",
                        "tool": "done",
                        "args": {},
                        "final_text": "Recovered after transient LLM error.",
                    }
                )

        with patch("app.core.llm.LLMProvider", FlakyProvider):
            ctx = AgentContext(
                user_message="check",
                primary=_primary(),
                max_iterations=5,
            )
            result = await run_agent_loop(ctx, default_tool_set())

        assert result.final_text == "Recovered after transient LLM error."
        assert result.stopped is False
        assert result.iterations == 1

    @pytest.mark.asyncio
    async def test_simple_shell_then_done(self, patch_llm):
        patch_llm(
            [
                {
                    "thinking": "check uptime",
                    "tool": "shell",
                    "args": {"cmd": "uptime"},
                    "final_text": "",
                },
                {
                    "thinking": "finish",
                    "tool": "done",
                    "args": {},
                    "final_text": "Uptime observed.",
                },
            ]
        )
        conn = FakeSSHConn(default=FakeRunResult(stdout="1d 2h\n", exit_status=0))
        events: list[dict] = []

        async def emit(ev):
            events.append(ev)

        ctx = AgentContext(
            user_message="how long has it been up?",
            primary=_primary(ssh_conn=conn),
            emit=emit,
        )
        result = await run_agent_loop(ctx, default_tool_set())
        assert result.final_text == "Uptime observed."
        assert result.iterations == 2
        assert result.tool_calls == 1
        assert conn.calls == ["uptime"]

        # Event shape check
        event_types = [e["type"] for e in events]
        assert "agent_tool_call" in event_types
        assert "agent_tool_result" in event_types

        # ToolResult.data must be forwarded on the WS event so the UI can
        # render exit_code / target badges without parsing raw output.
        tool_results = [e for e in events if e["type"] == "agent_tool_result"]
        assert tool_results, "expected at least one agent_tool_result"
        for ev in tool_results:
            assert "data" in ev, f"missing data in event: {ev}"
            assert isinstance(ev["data"], dict)
        # Shell tool populates exit_code in its data payload.
        shell_result = next(
            (e for e in tool_results if e.get("tool") == "shell"), None
        )
        assert shell_result is not None
        assert "exit_code" in shell_result["data"]

    @pytest.mark.asyncio
    async def test_max_iterations_stops_loop(self, patch_llm):
        # Scripted LLM that never says done — should hit max_iterations.
        patch_llm(
            [
                {
                    "thinking": "loop",
                    "tool": "shell",
                    "args": {"cmd": "ls"},
                    "final_text": "",
                }
            ]
            * 20
        )
        conn = FakeSSHConn()
        ctx = AgentContext(
            user_message="loop",
            primary=_primary(ssh_conn=conn),
            max_iterations=3,
        )
        result = await run_agent_loop(ctx, default_tool_set())
        assert result.stopped is True
        assert result.stop_reason == "max_iterations"
        assert result.iterations == 3

    @pytest.mark.asyncio
    async def test_unknown_tool_feeds_error_to_llm(self, patch_llm):
        patch_llm(
            [
                {
                    "thinking": "invalid tool",
                    "tool": "nonexistent_tool",
                    "args": {},
                    "final_text": "",
                },
                {
                    "thinking": "giving up",
                    "tool": "done",
                    "args": {},
                    "final_text": "Tool unavailable.",
                },
            ]
        )
        ctx = AgentContext(
            user_message="try something",
            primary=_primary(),
        )
        result = await run_agent_loop(ctx, default_tool_set())
        assert result.iterations == 2
        assert result.final_text == "Tool unavailable."

    @pytest.mark.asyncio
    async def test_invalid_args_dont_crash_loop(self, patch_llm):
        patch_llm(
            [
                # Missing required 'cmd' arg for shell tool
                {
                    "thinking": "wrong args",
                    "tool": "shell",
                    "args": {"target": "primary"},
                    "final_text": "",
                },
                {
                    "thinking": "recover",
                    "tool": "done",
                    "args": {},
                    "final_text": "Handled.",
                },
            ]
        )
        ctx = AgentContext(
            user_message="test",
            primary=_primary(),
        )
        result = await run_agent_loop(ctx, default_tool_set())
        assert result.iterations == 2
        assert result.final_text == "Handled."

    @pytest.mark.asyncio
    async def test_stop_requested_halts_loop(self, patch_llm):
        patch_llm(
            [
                {
                    "thinking": "keep going",
                    "tool": "shell",
                    "args": {"cmd": "ls"},
                    "final_text": "",
                }
            ]
            * 10
        )
        stop_flag = {"stop": False}

        def stop_req():
            return stop_flag["stop"]

        async def _trip_stop_after_first_call():
            # Trip on second iteration: first iteration executes shell,
            # then stop_requested() returns True at the top of iter 2.
            stop_flag["stop"] = True

        conn = FakeSSHConn()

        async def emit(ev):
            if ev["type"] == "agent_tool_result":
                await _trip_stop_after_first_call()

        ctx = AgentContext(
            user_message="do stuff",
            primary=_primary(ssh_conn=conn),
            emit=emit,
            stop_requested=stop_req,
            max_iterations=10,
        )
        result = await run_agent_loop(ctx, default_tool_set())
        assert result.stopped is True
        assert result.stop_reason == "user_stop"


# ---------------------------------------------------------------------------
# Target routing in the loop
# ---------------------------------------------------------------------------


class TestAgentLoopTargets:
    @pytest.mark.asyncio
    async def test_routes_to_extra_target(self, patch_llm):
        patch_llm(
            [
                {
                    "thinking": "check worker",
                    "tool": "shell",
                    "args": {"cmd": "hostname", "target": "worker-1"},
                    "final_text": "",
                },
                {
                    "thinking": "done",
                    "tool": "done",
                    "args": {},
                    "final_text": "OK.",
                },
            ]
        )
        primary_conn = FakeSSHConn(default=FakeRunResult(stdout="main", exit_status=0))
        worker_conn = FakeSSHConn(default=FakeRunResult(stdout="worker", exit_status=0))
        extras = {
            "worker-1": ServerTarget(
                name="worker-1",
                server_id=2,
                display_name="srv-worker-1",
                ssh_conn=worker_conn,
                is_primary=False,
            )
        }
        ctx = AgentContext(
            user_message="check workers",
            primary=_primary(ssh_conn=primary_conn),
            extras=extras,
        )
        result = await run_agent_loop(ctx, default_tool_set())
        assert result.iterations == 2
        assert worker_conn.calls == ["hostname"]
        assert primary_conn.calls == []  # primary untouched


# ---------------------------------------------------------------------------
# System prompt contract
# ---------------------------------------------------------------------------


class TestAgentSystemPrompt:
    """Guard the pieces of the system prompt that other parts of the
    product rely on. We do NOT pin the exact wording — just the must-have
    directives so future rewrites don't silently regress behaviour."""

    def test_system_prompt_enforces_russian_output(self):
        # Regression: the operator works in Russian and user-visible agent
        # strings (thinking, final_text, ask_user question, todo content)
        # must be produced in Russian. Losing this directive silently
        # re-introduces mixed-language UX.
        prompt = build_system_prompt(
            tools=default_tool_set(),
            primary=_primary(),
            extras={},
        )
        assert "Russian" in prompt, (
            "system prompt must force Russian output for user-facing fields"
        )
        # The policy block references the four user-visible fields so the
        # model knows which strings to translate.
        for field in ("thinking", "final_text", "ask_user", "todo"):
            assert field in prompt, (
                f"language policy must name the user-facing field {field!r}"
            )

    def test_system_prompt_inlines_memory_context(self):
        # Nova must be able to read persistent server memory so it can
        # skip re-discovery (configs, layouts, risks). The consumer
        # loads a ServerMemoryCard block and passes it as
        # ``memory_context`` — the builder must inline it verbatim
        # under the "Persistent server memory" heading.
        memory = (
            "Сервер: prod-db (10.0.0.5)\n"
            "Тип: postgres 14; конфиг /etc/postgresql/14/main/postgresql.conf\n"
            "Риски: WAL архив на /mnt/wal — не заполнять >80%"
        )
        prompt = build_system_prompt(
            tools=default_tool_set(),
            primary=_primary(),
            extras={},
            memory_context=memory,
        )
        assert "Persistent server memory" in prompt, (
            "system prompt must introduce the memory block with a heading"
        )
        # Every line of the card must survive injection so the LLM can
        # actually read the config path / risk notes.
        for line in memory.splitlines():
            assert line in prompt, f"memory line missing from prompt: {line!r}"

    def test_system_prompt_memory_block_has_fallback_when_empty(self):
        # Empty memory still renders a placeholder so the model
        # understands the section exists and knows to build it up via
        # `remember`.
        prompt = build_system_prompt(
            tools=default_tool_set(),
            primary=_primary(),
            extras={},
            memory_context="",
        )
        assert "Persistent server memory" in prompt
        assert "remember" in prompt  # pointer to the tool that grows memory
