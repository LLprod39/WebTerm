"""
Pydantic schemas for the Terminal Agent (Nova).

Every LLM round-trip in the agent loop is validated against
:class:`AgentStep`: the model picks a tool, optionally emits reasoning,
and either calls a tool or signals completion via the ``done`` pseudo-tool.

Unlike the legacy planner schemas (:mod:`servers.services.terminal_ai.schemas`),
the agent never returns a full plan — just the next action. This keeps
each LLM call cheap and adaptive.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

# ---------------------------------------------------------------------------
# Todo items (the agent maintains a live checklist visible to the user)
# ---------------------------------------------------------------------------

TodoStatus = Literal["pending", "in_progress", "completed", "cancelled"]


class Todo(BaseModel):
    """A single entry in the agent's live todo list."""

    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    id: str = Field(min_length=1, max_length=64)
    content: str = Field(min_length=1, max_length=500)
    status: TodoStatus = "pending"

    @field_validator("status", mode="before")
    @classmethod
    def _normalise_status(cls, value: Any) -> str:
        raw = str(value or "").strip().lower()
        allowed = {"pending", "in_progress", "completed", "cancelled"}
        return raw if raw in allowed else "pending"


# ---------------------------------------------------------------------------
# Tool call + result (the unit of exchange between loop and tools)
# ---------------------------------------------------------------------------


class ToolCall(BaseModel):
    """A request from the agent to invoke a specific tool."""

    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    tool: str = Field(min_length=1, max_length=64)
    """Name of the tool to invoke (must exist in the registry)."""

    args: dict[str, Any] = Field(default_factory=dict)
    """Arguments passed to the tool (validated against tool.args_schema)."""


class ToolResult(BaseModel):
    """Outcome of a tool invocation, fed back into the agent as an
    observation on the next turn.

    Fields are designed to round-trip cleanly through the LLM:
      - ``ok``: quick success/failure indicator.
      - ``output``: short human-readable summary (what the LLM actually reads).
      - ``data``: optional structured payload for downstream processing
        (e.g. grep matches, file size). Not fed back into the LLM by default.
      - ``error``: failure reason when ``ok=False``.
    """

    model_config = ConfigDict(extra="ignore")

    ok: bool = True
    output: str = ""
    data: dict[str, Any] | None = None
    error: str | None = None
    # Optional hint to the loop: stop calling tools because something
    # catastrophic happened (e.g. SSH disconnected).
    fatal: bool = False


# ---------------------------------------------------------------------------
# Agent step (the LLM's response on every turn)
# ---------------------------------------------------------------------------


class AgentStep(BaseModel):
    """One turn of the ReAct loop.

    The LLM either picks a tool to call OR signals completion by emitting
    ``tool="done"`` with ``final_text`` populated.

    ``thinking`` is optional and surfaced in the UI as a collapsible block
    so the user can follow the agent's reasoning. Keep it short — long
    thoughts inflate tokens without adding value.
    """

    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    thinking: str = Field(default="", max_length=2000)
    tool: str = Field(min_length=1, max_length=64)
    args: dict[str, Any] = Field(default_factory=dict)
    # When tool == "done": final assistant reply to the user.
    final_text: str = Field(default="", max_length=6000)


# ---------------------------------------------------------------------------
# Aggregate results (what the loop returns to the consumer)
# ---------------------------------------------------------------------------


class AgentResult(BaseModel):
    """Final outcome of :func:`run_agent_loop`."""

    model_config = ConfigDict(extra="ignore")

    final_text: str = ""
    iterations: int = 0
    tool_calls: int = 0
    stopped: bool = False  # True when halted via budget/interrupt, not done
    stop_reason: str = ""
    todos: list[Todo] = Field(default_factory=list)
