"""Internal helpers for the Nova terminal agent ReAct loop."""

from __future__ import annotations

import asyncio
import contextlib
import logging

from pydantic import ValidationError

from servers.services.terminal_ai.agent.schemas import (
    AgentStep,
    ToolResult,
)
from servers.services.terminal_ai.agent.tools.base import (
    TerminalTool,
    ToolContext,
)
from servers.services.terminal_ai.schemas import parse_or_repair

logger = logging.getLogger(__name__)

# Cap on LLM output size before we force-terminate the stream to avoid
# runaway responses. The loop accepts anything that parses as JSON first.
LLM_OUTPUT_CHAR_CAP = 10_000

_LLM_RETRY_BACKOFF_SEC = (1.0,)


def is_retryable_llm_error(exc: Exception) -> bool:
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


async def llm_next_step(system_prompt: str, user_prompt: str) -> AgentStep:
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


async def llm_next_step_with_retry(
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
                llm_next_step(system_prompt, user_prompt),
                timeout=timeout_sec,
            )
        except TimeoutError:
            raise
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            if attempt >= max_attempts - 1 or not is_retryable_llm_error(exc):
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


async def invoke_tool(
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
            output=(f"Unknown tool: {step.tool!r}. Valid: " + ", ".join(sorted(tools.keys()))),
            error=f"unknown tool {step.tool}",
        )

    try:
        validated = tool.args_schema.model_validate(step.args or {})
    except ValidationError as exc:
        # Return a concise error the LLM can learn from.
        errors = exc.errors(include_url=False)
        summary = "; ".join(
            f"{'.'.join(str(p) for p in err.get('loc', ())) or 'root'}: {err.get('msg', '')}" for err in errors[:5]
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
    except TimeoutError:
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


# Private aliases kept for any in-module historical references / tests that
# monkeypatch underscore-prefixed names on the loop module via re-exports.
_is_retryable_llm_error = is_retryable_llm_error
_llm_next_step = llm_next_step
_llm_next_step_with_retry = llm_next_step_with_retry
_invoke_tool = invoke_tool

__all__ = [
    "LLM_OUTPUT_CHAR_CAP",
    "invoke_tool",
    "is_retryable_llm_error",
    "llm_next_step",
    "llm_next_step_with_retry",
]
