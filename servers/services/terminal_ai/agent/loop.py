"""
Nova — the Terminal Agent ReAct loop.

Entry point :func:`run_agent_loop` drives a single user turn to
completion. It repeatedly asks the LLM for the next :class:`AgentStep`,
dispatches the chosen tool, feeds the observation back, and stops when
the model emits ``tool="done"`` or hits a budget guard.

Events
------
Every significant loop event is forwarded to the consumer via the
``emit`` callback on :class:`~servers.services.terminal_ai.agent.tools.base.ToolContext`:

- ``agent_start``        — loop began, initial todos/targets sent
- ``agent_thinking``     — LLM's short reasoning snippet
- ``agent_tool_call``    — tool name + args about to be executed
- ``agent_tool_result``  — tool outcome (ok, output snippet, data)
- ``agent_todo_update``  — live checklist changed
- ``agent_done``         — loop finished normally
- ``agent_error``        — unrecoverable failure
- ``agent_stopped``      — budget or user-interrupt halt

The consumer maps these to WebSocket messages.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from servers.agent_budgets import (
    NOVA_COMPACT_AFTER_TURNS,
    NOVA_DEFAULT_ITERATION_TIMEOUT_SEC,
    NOVA_DEFAULT_MAX_ITERATIONS,
    NOVA_DEFAULT_TOTAL_TIMEOUT_SEC,
)
from servers.services.terminal_ai.agent.loop_helpers import (
    invoke_tool as _invoke_tool,
)
from servers.services.terminal_ai.agent.loop_helpers import (
    llm_next_step_with_retry as _llm_next_step_with_retry,
)
from servers.services.terminal_ai.agent.prompts import (
    build_partial_stop_summary,
    build_system_prompt,
    build_user_turn_prompt,
    compact_agent_history,
)
from servers.services.terminal_ai.agent.schemas import (
    AgentResult,
    Todo,
)
from servers.services.terminal_ai.agent.tools.base import (
    ServerTarget,
    TerminalTool,
    ToolContext,
    UserPromptRequest,
)

logger = logging.getLogger(__name__)

# Hard limits. The loop will halt itself when any is exceeded.
DEFAULT_MAX_ITERATIONS = NOVA_DEFAULT_MAX_ITERATIONS
DEFAULT_ITERATION_TIMEOUT_SEC = NOVA_DEFAULT_ITERATION_TIMEOUT_SEC  # wall-clock per iteration (LLM + tool)
DEFAULT_TOTAL_TIMEOUT_SEC = float(NOVA_DEFAULT_TOTAL_TIMEOUT_SEC)  # wall-clock for the whole loop


# ---------------------------------------------------------------------------
# Context dataclass — everything the consumer needs to hand the loop
# ---------------------------------------------------------------------------


@dataclass
class AgentContext:
    """Bundle of inputs for :func:`run_agent_loop`.

    The consumer builds one instance per user request and wires up the
    async callbacks.
    """

    user_message: str
    primary: ServerTarget
    extras: dict[str, ServerTarget] = field(default_factory=dict)
    user_id: int | None = None

    # Async callbacks (see ToolContext docstrings).
    emit: Callable[[dict[str, Any]], Awaitable[None]] | None = None
    prompt_user: Callable[[UserPromptRequest], Awaitable[str | None]] | None = None
    open_target: Callable[[str], Awaitable[Any | None]] | None = None

    # External stop signal set by the consumer when the user types `/stop`.
    stop_requested: Callable[[], bool] | None = None

    # Optional rules/context block from the server's GlobalServerRules.
    rules_context: str = ""

    # Layered-server-memory block rendered once per run from the
    # authorised targets' ServerMemoryCards. Empty string = no prior
    # knowledge (the consumer is responsible for loading / respecting
    # the memory_enabled user toggle).
    memory_context: str = ""

    session_context: str = ""
    recent_activity_context: str = ""
    ui_context_payload: dict[str, Any] = field(default_factory=dict)

    # Tuning knobs.
    max_iterations: int = DEFAULT_MAX_ITERATIONS
    iteration_timeout_sec: float = DEFAULT_ITERATION_TIMEOUT_SEC
    total_timeout_sec: float = DEFAULT_TOTAL_TIMEOUT_SEC
    dry_run: bool = False
    sudo_policy: str = "disabled"
    compact_after_turns: int = NOVA_COMPACT_AFTER_TURNS


# ---------------------------------------------------------------------------
# Public: main loop
# ---------------------------------------------------------------------------


async def run_agent_loop(
    ctx: AgentContext,
    tools: dict[str, TerminalTool],
) -> AgentResult:
    """Drive the ReAct loop until the agent says ``done`` or hits a budget.

    This function never raises into the consumer — failures are captured
    as :class:`AgentResult` fields so the WebSocket thread can shut down
    cleanly and notify the user.
    """
    loop_start = asyncio.get_running_loop().time()

    tool_ctx = ToolContext(
        primary=ctx.primary,
        extras=ctx.extras,
        user_id=ctx.user_id,
        emit=ctx.emit,
        prompt_user=ctx.prompt_user,
        open_target=ctx.open_target,
        dry_run=ctx.dry_run,
        sudo_policy=ctx.sudo_policy,
    )

    system_prompt = build_system_prompt(
        tools=tools,
        primary=ctx.primary,
        extras=ctx.extras,
        rules_context=ctx.rules_context,
        memory_context=ctx.memory_context,
        sudo_policy=ctx.sudo_policy,
    )

    history: list[dict[str, Any]] = []
    iterations = 0
    tool_calls = 0
    final_text = ""
    stopped = False
    stop_reason = ""

    if ctx.emit is not None:
        await ctx.emit(
            {
                "type": "agent_start",
                "primary_target": ctx.primary.name,
                "extras": [t.name for t in ctx.extras.values()],
                "goal": ctx.user_message[:500],
                "context": dict(ctx.ui_context_payload) if ctx.ui_context_payload else {},
            }
        )

    try:
        while iterations < ctx.max_iterations:
            # Wall-clock budget check.
            elapsed = asyncio.get_running_loop().time() - loop_start
            if elapsed > ctx.total_timeout_sec:
                stopped = True
                stop_reason = "total_timeout"
                break

            # User /stop check.
            if ctx.stop_requested is not None and ctx.stop_requested():
                stopped = True
                stop_reason = "user_stop"
                break

            iterations += 1
            user_prompt = build_user_turn_prompt(
                user_message=ctx.user_message,
                history=history,
                session_context=ctx.session_context,
                recent_activity_context=ctx.recent_activity_context,
            )

            try:
                step = await _llm_next_step_with_retry(
                    system_prompt,
                    user_prompt,
                    timeout_sec=ctx.iteration_timeout_sec,
                )
            except TimeoutError:
                stopped = True
                stop_reason = "llm_timeout"
                break
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
                logger.warning("agent LLM call failed: %s", exc)
                if ctx.emit is not None:
                    await ctx.emit({"type": "agent_error", "iteration": iterations, "message": str(exc)[:400]})
                stopped = True
                stop_reason = "llm_error"
                break

            # Emit thinking (optional, collapsible in UI).
            if ctx.emit is not None and step.thinking.strip():
                await ctx.emit(
                    {
                        "type": "agent_thinking",
                        "iteration": iterations,
                        "text": step.thinking,
                    }
                )

            # Done pseudo-tool: finalise and exit.
            #
            # The system prompt instructs the LLM to emit ``final_text``
            # at the top level of the step JSON, but because the tool
            # catalogue *also* advertises ``done`` with a ``final_text``
            # arg (see DoneArgs / DoneTool), weaker models often pack
            # the summary into ``step.args["final_text"]`` instead.
            # Accept both shapes so the user never loses the answer.
            # As a last resort, surface a generic completion notice so
            # the UI isn't left silent after a successful run.
            if step.tool == "done":
                candidate = (step.final_text or "").strip()
                if not candidate:
                    arg_text = step.args.get("final_text") if step.args else None
                    if isinstance(arg_text, str):
                        candidate = arg_text.strip()
                if not candidate:
                    candidate = "Задача выполнена."
                final_text = candidate
                break

            # Emit tool call.
            if ctx.emit is not None:
                await ctx.emit(
                    {
                        "type": "agent_tool_call",
                        "iteration": iterations,
                        "tool": step.tool,
                        "args": step.args,
                    }
                )

            history.append(
                {
                    "turn": iterations,
                    "role": "tool_call",
                    "content": {
                        "tool": step.tool,
                        "args": step.args,
                        "thinking": step.thinking,
                    },
                }
            )

            # Execute.
            result = await _invoke_tool(step, tools, tool_ctx, timeout_sec=ctx.iteration_timeout_sec)
            tool_calls += 1

            # Emit tool result. We forward ``data`` so the UI can show
            # structured metadata (exit_code, target, ...) as badges
            # instead of the user having to grep the raw output.
            if ctx.emit is not None:
                await ctx.emit(
                    {
                        "type": "agent_tool_result",
                        "iteration": iterations,
                        "tool": step.tool,
                        "ok": result.ok,
                        "output": result.output[:2000],
                        "error": result.error,
                        "data": dict(result.data) if result.data else {},
                    }
                )

            history.append(
                {
                    "turn": iterations,
                    "role": "tool_result",
                    "content": result.output,
                }
            )
            # Compact in-place so subsequent turns and partial reports see summary.
            history[:] = compact_agent_history(
                history,
                compact_after=int(
                    getattr(ctx, "compact_after_turns", NOVA_COMPACT_AFTER_TURNS) or NOVA_COMPACT_AFTER_TURNS
                ),
            )

            if result.fatal:
                stopped = True
                stop_reason = "fatal_tool_error"
                break
        else:
            # while-else triggers when loop exhausts without break
            stopped = True
            stop_reason = "max_iterations"

    except asyncio.CancelledError:
        stopped = True
        stop_reason = "cancelled"
        raise
    finally:
        todos_out = [Todo.model_validate(t) for t in tool_ctx.todos]
        # Always produce a non-empty Russian partial summary when the loop
        # stops without a normal ``done`` final_text (budget/timeout/error).
        if stopped and not (final_text or "").strip():
            final_text = build_partial_stop_summary(
                user_message=ctx.user_message,
                history=history,
                stop_reason=stop_reason,
                iterations=iterations,
                tool_calls=tool_calls,
                todos=todos_out,
            )
        if ctx.emit is not None:
            if stopped:
                await ctx.emit(
                    {
                        "type": "agent_stopped",
                        "reason": stop_reason,
                        "iterations": iterations,
                        "tool_calls": tool_calls,
                        "final_text": final_text,
                    }
                )
            else:
                await ctx.emit(
                    {
                        "type": "agent_done",
                        "final_text": final_text,
                        "iterations": iterations,
                        "tool_calls": tool_calls,
                    }
                )

    return AgentResult(
        final_text=final_text,
        iterations=iterations,
        tool_calls=tool_calls,
        stopped=stopped,
        stop_reason=stop_reason,
        todos=todos_out,
    )


# Historical private names re-exported for tests that monkeypatch this module.
from servers.services.terminal_ai.agent.loop_helpers import (  # noqa: E402,F401
    is_retryable_llm_error as _is_retryable_llm_error,
)

__all__ = ["AgentContext", "AgentResult", "run_agent_loop"]
