"""
Sanitisation helpers for Terminal AI prompt builders.

All untrusted text (terminal tail, command output, DB-sourced knowledge,
chat history, user message fragments injected back via "user reply")
MUST flow through :func:`sanitize_for_prompt` before being embedded into a
prompt template.
"""

from __future__ import annotations

from app.agent_kernel.memory.redaction import (
    sanitize_observation_text,
    sanitize_prompt_context_text,
)

EMPTY_PLACEHOLDER = "(пусто)"
HISTORY_PLACEHOLDER = "(начало диалога)"


def sanitize_for_prompt(text: str | None, *, mode: str = "context", fallback: str | None = None) -> str:
    """Redact secrets + neutralise prompt-injection in untrusted text.

    ``mode``:
      - ``"context"``: prompt-context rails (role/system line neutralisation
        in addition to observation-level filtering). Use for DB knowledge,
        rules, recent history.
      - ``"observation"``: observation rails only. Use for raw command
        output / terminal tail.

    ``fallback`` is returned verbatim when the sanitized text is empty.
    """
    raw = "" if text is None else str(text)
    if not raw.strip():
        return fallback if fallback is not None else ""
    sanitized = sanitize_observation_text(raw).text if mode == "observation" else sanitize_prompt_context_text(raw).text
    return sanitized if sanitized.strip() else (fallback if fallback is not None else "")
