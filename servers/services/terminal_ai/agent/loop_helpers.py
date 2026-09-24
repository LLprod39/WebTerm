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
    # Schema hiccups (missing tool / trunc JSON) often succeed on a fresh attempt.
    if "llm output invalid" in message or "no json object" in message:
        return True
    if "429" in message or "resource exhausted" in message or "rate" in message:
        return True
    return any(code in message for code in ("500", "502", "503", "504", "internal error", "service unavailable"))


async def llm_next_step(system_prompt: str, user_prompt: str, *, execution_context=None) -> AgentStep:
    """Call the planner LLM once and parse its response.

    Uses JSON mode so we get a guaranteed-valid JSON object on the wire.
    Falls back to :func:`parse_or_repair` for provider hiccups.
    """
    from app.core.llm import LLMProvider

    llm = LLMProvider()
    out = ""
    # #region agent log
    _chunk_n = 0
    _t0 = asyncio.get_running_loop().time()
    # #endregion
    async for chunk in llm.stream_chat(
        user_prompt,
        model="auto",
        purpose="terminal_agent",
        system_prompt=system_prompt,
        json_mode=True,
        execution_context=execution_context,
    ):
        out += chunk
        # #region agent log
        _chunk_n += 1
        if _chunk_n in (1, 5, 20) or len(out) > LLM_OUTPUT_CHAR_CAP:
            try:
                import json as _json
                import time as _time
                from pathlib import Path as _Path

                _log = {
                    "sessionId": "a0b238",
                    "runId": "pre-fix",
                    "hypothesisId": "B",
                    "location": "loop_helpers.py:llm_stream",
                    "message": "nova LLM stream progress",
                    "data": {
                        "chunks": _chunk_n,
                        "out_chars": len(out),
                        "elapsed_sec": round(asyncio.get_running_loop().time() - _t0, 3),
                    },
                    "timestamp": int(_time.time() * 1000),
                }
                for _p in (_Path("/workspace/debug-a0b238.log"), _Path(__file__).resolve().parents[4] / "debug-a0b238.log"):
                    try:
                        with _p.open("a", encoding="utf-8") as _f:
                            _f.write(_json.dumps(_log, ensure_ascii=False) + "\n")
                        break
                    except Exception:
                        continue
            except Exception:
                pass
        # #endregion
        if len(out) > LLM_OUTPUT_CHAR_CAP:
            break

    if (out or "").strip().lower().startswith("error:"):
        raise RuntimeError(out.strip()[:500])

    step, err = parse_or_repair(out, AgentStep)
    if step is None:
        # #region agent log
        try:
            import json as _json
            import time as _time
            from pathlib import Path as _Path

            _log = {
                "sessionId": "a0b238",
                "runId": "post-fix",
                "hypothesisId": "B",
                "location": "loop_helpers.py:llm_parse_fail",
                "message": "nova LLM JSON parse/validate failed",
                "data": {
                    "error": str(err)[:300],
                    "out_chars": len(out or ""),
                    "out_preview": (out or "")[:240],
                },
                "timestamp": int(_time.time() * 1000),
            }
            for _p in (_Path("/workspace/debug-a0b238.log"), _Path(__file__).resolve().parents[4] / "debug-a0b238.log"):
                try:
                    with _p.open("a", encoding="utf-8") as _f:
                        _f.write(_json.dumps(_log, ensure_ascii=False) + "\n")
                    break
                except Exception:
                    continue
        except Exception:
            pass
        # #endregion
        raise ValueError(f"LLM output invalid: {err}")
    assert isinstance(step, AgentStep)
    return step


async def llm_next_step_with_retry(
    system_prompt: str,
    user_prompt: str,
    *,
    timeout_sec: float,
    max_attempts: int = 2,
    execution_context=None,
) -> AgentStep:
    last_exc: Exception | None = None
    for attempt in range(max_attempts):
        try:
            return await asyncio.wait_for(
                llm_next_step(system_prompt, user_prompt, execution_context=execution_context),
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
        # Shell may pause up to 300s on a one-shot safety approval before the
        # command runs; without this the outer wait_for (180s) cancels mid-prompt.
        if step.tool == "shell":
            shell_t = getattr(validated, "timeout", None)
            try:
                shell_budget = float(shell_t) if shell_t is not None else 30.0
            except (TypeError, ValueError):
                shell_budget = 30.0
            effective_timeout = max(effective_timeout, 305.0 + max(1.0, shell_budget))
        # #region agent log
        try:
            import json as _json
            import time as _time
            from pathlib import Path as _Path

            _shell_timeout = getattr(validated, "timeout", None)
            _log = {
                "sessionId": "a0b238",
                "runId": "post-fix",
                "hypothesisId": "C",
                "location": "loop_helpers.py:invoke_tool_start",
                "message": "nova invoke_tool start",
                "data": {
                    "tool": step.tool,
                    "outer_timeout_sec": effective_timeout,
                    "shell_arg_timeout": _shell_timeout,
                    "approval_budget_gap": (
                        step.tool == "shell" and float(effective_timeout) < 300.0
                    ),
                },
                "timestamp": int(_time.time() * 1000),
            }
            for _p in (_Path("/workspace/debug-a0b238.log"), _Path(__file__).resolve().parents[4] / "debug-a0b238.log"):
                try:
                    with _p.open("a", encoding="utf-8") as _f:
                        _f.write(_json.dumps(_log, ensure_ascii=False) + "\n")
                    break
                except Exception:
                    continue
        except Exception:
            pass
        # #endregion
        _t0 = asyncio.get_running_loop().time()
        result = await asyncio.wait_for(tool.run(validated, ctx), timeout=effective_timeout)
        # #region agent log
        try:
            import json as _json
            import time as _time
            from pathlib import Path as _Path

            _log = {
                "sessionId": "a0b238",
                "runId": "pre-fix",
                "hypothesisId": "A,C",
                "location": "loop_helpers.py:invoke_tool_ok",
                "message": "nova invoke_tool finished",
                "data": {
                    "tool": step.tool,
                    "elapsed_sec": round(asyncio.get_running_loop().time() - _t0, 3),
                    "ok": bool(getattr(result, "ok", False)),
                    "error": (getattr(result, "error", None) or "")[:200],
                    "exit_code": (getattr(result, "data", None) or {}).get("exit_code")
                    if isinstance(getattr(result, "data", None), dict)
                    else None,
                },
                "timestamp": int(_time.time() * 1000),
            }
            for _p in (_Path("/workspace/debug-a0b238.log"), _Path(__file__).resolve().parents[4] / "debug-a0b238.log"):
                try:
                    with _p.open("a", encoding="utf-8") as _f:
                        _f.write(_json.dumps(_log, ensure_ascii=False) + "\n")
                    break
                except Exception:
                    continue
        except Exception:
            pass
        # #endregion
        return result
    except TimeoutError:
        # #region agent log
        try:
            import json as _json
            import time as _time
            from pathlib import Path as _Path

            _log = {
                "sessionId": "a0b238",
                "runId": "pre-fix",
                "hypothesisId": "C",
                "location": "loop_helpers.py:invoke_tool_timeout",
                "message": "nova outer tool wait_for timeout",
                "data": {
                    "tool": step.tool,
                    "outer_timeout_sec": effective_timeout,
                    "note": "shell approval waits 300s but outer cap may be 180s",
                },
                "timestamp": int(_time.time() * 1000),
            }
            for _p in (_Path("/workspace/debug-a0b238.log"), _Path(__file__).resolve().parents[4] / "debug-a0b238.log"):
                try:
                    with _p.open("a", encoding="utf-8") as _f:
                        _f.write(_json.dumps(_log, ensure_ascii=False) + "\n")
                    break
                except Exception:
                    continue
        except Exception:
            pass
        # #endregion
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
