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
import contextlib
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from loguru import logger
from pydantic import ValidationError

from servers.services.terminal_ai.agent.prompts import (
    build_system_prompt,
    build_user_turn_prompt,
)
from servers.services.terminal_ai.agent.schemas import (
    AgentResult,
    AgentStep,
    Todo,
    ToolResult,
)
from servers.services.terminal_ai.agent.tools.base import (
    ServerTarget,
    TerminalTool,
    ToolContext,
    UserPromptRequest,
)
from servers.services.terminal_ai.schemas import parse_or_repair

logger = logging.getLogger(__name__)

# Hard limits. The loop will halt itself when any is exceeded.
DEFAULT_MAX_ITERATIONS = 30
DEFAULT_ITERATION_TIMEOUT_SEC = 180.0  # wall-clock per iteration (LLM + tool)
DEFAULT_TOTAL_TIMEOUT_SEC = 1800.0  # wall-clock for the whole loop (30 min)

# Cap on LLM output size before we force-terminate the stream to avoid
# runaway responses. The loop accepts anything that parses as JSON first.
LLM_OUTPUT_CHAR_CAP = 10_000


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


# ---------------------------------------------------------------------------
# Internal: LLM round-trip
# ---------------------------------------------------------------------------


_LLM_RETRY_BACKOFF_SEC = (1.0,)


def _is_retryable_llm_error(exc: Exception) -> bool:
    with contextlib.suppress(Exception):
        from app.core.llm import _is_retryable_error

        return bool(_is_retryable_error(exc))

    message = str(exc).lower()
    if isinstance(exc, (TimeoutError, asyncio.TimeoutError)):
        return True
    if "timeout" in message or "timed out" in message:
        return True
    if "429" in message or "resource exhausted" in message or "rate" in message:
        return True
    return any(code in message for code in ("500", "502", "503", "504", "internal error", "service unavailable"))


async def _llm_next_step_with_retry(
    system_prompt: str,
    user_prompt: str,
    *,
    timeout_sec: float,
    max_attempts: int = 2,
) -> AgentStep:
    last_exc: Exception | None = None
    for attempt in range(max_attempts):
        try:
            return await asyncio.wait_for(
                _llm_next_step(system_prompt, user_prompt),
                timeout=timeout_sec,
            )
        except asyncio.TimeoutError:
            raise
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            if attempt >= max_attempts - 1 or not _is_retryable_llm_error(exc):
                raise
            delay = _LLM_RETRY_BACKOFF_SEC[min(attempt, len(_LLM_RETRY_BACKOFF_SEC) - 1)]
            logger.warning(
                "agent planner LLM transient failure (attempt %s/%s): %s; retry in %.1fs",
                attempt + 1,
                max_attempts,
                exc,
                delay,
            )
            await asyncio.sleep(delay)

    assert last_exc is not None
    raise last_exc


async def _llm_next_step(system_prompt: str, user_prompt: str) -> AgentStep:
    """Call the planner LLM once and parse its response.

    Uses JSON mode so we get a guaranteed-valid JSON object on the wire.
    Falls back to :func:`parse_or_repair` for provider hiccups.
    """
    from app.core.llm import LLMProvider

    llm = LLMProvider()
    out = ""
    async for chunk in llm.stream_chat(
        user_prompt,
        model="auto",
        purpose="terminal_agent",
        system_prompt=system_prompt,
        json_mode=True,
    ):
        out += chunk
        if len(out) > LLM_OUTPUT_CHAR_CAP:
            break

    if (out or "").strip().lower().startswith("error:"):
        raise RuntimeError(out.strip()[:500])

    step, err = parse_or_repair(out, AgentStep)
    if step is None:
        raise ValueError(f"LLM output invalid: {err}")
    assert isinstance(step, AgentStep)
    return step


# ---------------------------------------------------------------------------
# Internal: dispatch a tool call
# ---------------------------------------------------------------------------


async def _invoke_tool(
    step: AgentStep,
    tools: dict[str, TerminalTool],
    ctx: ToolContext,
    timeout_sec: float,
) -> ToolResult:
    """Validate args against the tool's pydantic schema and execute it."""
    tool = tools.get(step.tool)
    if tool is None:
        return ToolResult(
            ok=False,
            output=(
                f"Unknown tool: {step.tool!r}. Valid: "
                + ", ".join(sorted(tools.keys()))
            ),
            error=f"unknown tool {step.tool}",
        )

    try:
        validated = tool.args_schema.model_validate(step.args or {})
    except ValidationError as exc:
        # Return a concise error the LLM can learn from.
        errors = exc.errors(include_url=False)
        summary = "; ".join(
            f"{'.'.join(str(p) for p in err.get('loc', ())) or 'root'}: {err.get('msg', '')}"
            for err in errors[:5]
        )
        return ToolResult(
            ok=False,
            output=f"args validation failed: {summary}",
            error=summary,
        )

    try:
        effective_timeout = float(timeout_sec)
        ask_timeout = getattr(validated, "timeout_seconds", None)
        if step.tool == "ask_user" and isinstance(ask_timeout, int | float):
            effective_timeout = max(effective_timeout, float(ask_timeout) + 5.0)
        return await asyncio.wait_for(tool.run(validated, ctx), timeout=effective_timeout)
    except asyncio.TimeoutError:
        return ToolResult(
            ok=False,
            output=f"tool {step.tool!r} timed out after {effective_timeout:.0f}s",
            error="tool timeout",
        )
    except asyncio.CancelledError:
        raise
    except Exception as exc:  # noqa: BLE001 — tools must never crash the loop
        logger.warning("agent tool %s failed: %s", step.tool, exc)
        return ToolResult(
            ok=False,
            output=f"tool crashed: {type(exc).__name__}: {exc}",
            error=str(exc),
        )


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
    )

    system_prompt = build_system_prompt(
        tools=tools,
        primary=ctx.primary,
        extras=ctx.extras,
        rules_context=ctx.rules_context,
        memory_context=ctx.memory_context,
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
            except asyncio.TimeoutError:
                stopped = True
                stop_reason = "llm_timeout"
                break
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
                logger.warning("agent LLM call failed: %s", exc)
                if ctx.emit is not None:
                    await ctx.emit(
                        {"type": "agent_error", "iteration": iterations, "message": str(exc)[:400]}
                    )
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
            result = await _invoke_tool(
                step, tools, tool_ctx, timeout_sec=ctx.iteration_timeout_sec
            )
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
        if ctx.emit is not None:
            if stopped:
                await ctx.emit(
                    {
                        "type": "agent_stopped",
                        "reason": stop_reason,
                        "iterations": iterations,
                        "tool_calls": tool_calls,
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


__all__ = ["AgentContext", "AgentResult", "run_agent_loop"]
