"""Request-local LLM overrides shared by providers and feature layers."""

from __future__ import annotations

import contextvars

operator_thinking_mode: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "operator_thinking_mode",
    default=None,
)
