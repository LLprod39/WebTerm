"""
Pydantic response schemas for terminal AI LLM calls (F1-6).

Each schema corresponds to one LLM turn in the terminal AI orchestration
loop. ``parse_or_repair`` extracts a JSON object from raw LLM output
(stripping markdown fences, leading text, trailing garbage) and validates
it against the given pydantic model. On validation failure it returns
``(None, error_text)`` so the caller can decide whether to re-prompt
with a "your JSON was invalid" message.
"""

from __future__ import annotations

import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

# ---------------------------------------------------------------------------
# Planner response
# ---------------------------------------------------------------------------


class PlannedCommand(BaseModel):
    """One command suggested by the planner.

    ``exec_mode`` (F2-8) is an optional hint: ``"pty"`` (default) forces
    execution via the interactive shell (preserves cwd / env / aliases /
    shell state), ``"direct"`` signals a safe read-only probe eligible for
    stateless non-PTY exec. The v1 consumer treats this as informational
    only — dispatch still uses PTY. The policy layer
    (``servers.services.terminal_ai.policy.choose_exec_mode``) also
    re-derives this value defensively, so invalid values are ignored.
    """

    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    cmd: str = Field(min_length=1, max_length=2000)
    why: str = Field(default="", max_length=1000)
    exec_mode: Literal["pty", "direct"] = "pty"

    @field_validator("exec_mode", mode="before")
    @classmethod
    def _normalise_exec_mode(cls, value: Any) -> str:
        raw = str(value or "").strip().lower()
        return raw if raw in {"pty", "direct"} else "pty"


class TerminalPlanResponse(BaseModel):
    """Planner output: mode, assistant text and optional commands."""

    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    mode: Literal["answer", "execute", "ask"] = "answer"
    execution_mode: Literal["step", "fast", "auto"] = "step"
    assistant_text: str = Field(default="", max_length=6000)
    commands: list[PlannedCommand] = Field(default_factory=list, max_length=12)

    @field_validator("mode", mode="before")
    @classmethod
    def _normalise_mode(cls, value: Any) -> str:
        raw = str(value or "").strip().lower()
        return raw if raw in {"answer", "execute", "ask"} else "answer"

    @field_validator("execution_mode", mode="before")
    @classmethod
    def _normalise_execution_mode(cls, value: Any) -> str:
        raw = str(value or "").strip().lower()
        return raw if raw in {"step", "fast", "auto"} else "step"


# ---------------------------------------------------------------------------
# Recovery (on command failure)
# ---------------------------------------------------------------------------


class RecoveryDecision(BaseModel):
    """LLM decision after a command failed."""

    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    action: Literal["retry", "skip", "ask", "abort"] = "skip"
    cmd: str = Field(default="", max_length=2000)
    why: str = Field(default="", max_length=1000)
    question: str = Field(default="", max_length=1000)

    @field_validator("action", mode="before")
    @classmethod
    def _normalise_action(cls, value: Any) -> str:
        raw = str(value or "").strip().lower()
        return raw if raw in {"retry", "skip", "ask", "abort"} else "skip"


# ---------------------------------------------------------------------------
# Step-by-step decision (after each successful command)
# ---------------------------------------------------------------------------


class StepDecision(BaseModel):
    """LLM decision after every step in step-by-step mode (F1-9).

    Unified schema: covers both the *success-path* (continue / next / done /
    ask / abort) and the *error-path* (retry / skip / ask / abort) so the
    orchestrator can run a single LLM call per step instead of two
    (recovery + step-decide).

    Action semantics:
      - ``continue``: plan unchanged, execute next queued item
      - ``next``: insert ``next_cmd`` before the remaining plan (adaptive step)
      - ``retry``: replace the failed command with ``cmd`` and run again
      - ``skip``: failed command is non-critical, move on
      - ``done``: goal already reached, halt remaining plan
      - ``ask``: ask the user ``question`` and re-evaluate afterwards
      - ``abort``: unrecoverable — stop the entire run
    """

    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    action: Literal["continue", "next", "retry", "skip", "done", "ask", "abort"] = "continue"
    assistant_text: str = Field(default="", max_length=3000)
    next_cmd: str = Field(default="", max_length=2000)
    cmd: str = Field(default="", max_length=2000)
    why: str = Field(default="", max_length=1000)
    question: str = Field(default="", max_length=1000)

    @field_validator("action", mode="before")
    @classmethod
    def _normalise_action(cls, value: Any) -> str:
        raw = str(value or "").strip().lower()
        allowed = {"continue", "next", "retry", "skip", "done", "ask", "abort"}
        return raw if raw in allowed else "continue"


# ---------------------------------------------------------------------------
# Memory extraction
# ---------------------------------------------------------------------------


class MemoryExtraction(BaseModel):
    """LLM-extracted durable context for a server after a run."""

    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    summary: str = Field(default="", max_length=600)
    facts: list[str] = Field(default_factory=list, max_length=20)
    issues: list[str] = Field(default_factory=list, max_length=10)


# ---------------------------------------------------------------------------
# Robust JSON object extraction (shared with consumers)
# ---------------------------------------------------------------------------


def _extract_json_object(text: str) -> dict | None:
    """Extract the first JSON object from raw LLM text.

    Handles markdown fences (```json ... ```), leading prose, trailing
    garbage. Returns ``None`` if no object-shaped JSON is found.
    """
    if not text:
        return None
    cleaned = str(text).strip()
    # Strip markdown fences
    if cleaned.startswith("```"):
        first_nl = cleaned.index("\n") if "\n" in cleaned else len(cleaned)
        cleaned = cleaned[first_nl + 1 :]
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3]
    cleaned = cleaned.strip()

    # Fast path: the whole thing is a JSON object
    try:
        obj = json.loads(cleaned)
        return obj if isinstance(obj, dict) else None
    except (json.JSONDecodeError, ValueError):
        pass

    # Fallback: find first '{' and raw_decode
    brace_idx = cleaned.find("{")
    if brace_idx == -1:
        return None
    try:
        decoder = json.JSONDecoder()
        obj, _ = decoder.raw_decode(cleaned, brace_idx)
        return obj if isinstance(obj, dict) else None
    except (json.JSONDecodeError, ValueError):
        return None


def parse_or_repair(
    raw_text: str,
    schema: type[BaseModel],
) -> tuple[BaseModel | None, str]:
    """Parse raw LLM output into a pydantic schema instance.

    Returns a pair ``(instance, error)``:
      - ``(instance, "")`` on success
      - ``(None, reason)`` if the JSON is malformed or fails validation;
        ``reason`` is short and safe to embed into a repair-prompt.
    """
    obj = _extract_json_object(raw_text)
    if obj is None:
        return None, "no JSON object found in response"
    try:
        return schema.model_validate(obj), ""
    except ValidationError as exc:
        # Keep the error compact — it goes straight into a repair prompt.
        errors = exc.errors(include_url=False)
        summary = "; ".join(
            f"{'.'.join(str(p) for p in err.get('loc', ())) or 'root'}: {err.get('msg', '')}" for err in errors[:5]
        )
        return None, summary or "validation failed"
