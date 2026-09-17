"""Durable Nova conversation state for one SSH terminal session."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class NovaConversationState:
    """Follow-up context that survives across Nova turns on the same SSH."""

    todos: list[dict[str, Any]] = field(default_factory=list)
    compacted_history: list[dict[str, Any]] = field(default_factory=list)
    last_final_text: str = ""
    pending_user_messages: list[str] = field(default_factory=list)
    running: bool = False

    def reset(self) -> None:
        self.todos.clear()
        self.compacted_history.clear()
        self.last_final_text = ""
        self.pending_user_messages.clear()
        self.running = False

    def enqueue_interjection(self, message: str) -> None:
        text = str(message or "").strip()
        if text:
            self.pending_user_messages.append(text)

    def snapshot_todos(self) -> list[dict[str, Any]]:
        return [dict(item) for item in self.todos if isinstance(item, dict)]

    def snapshot_history(self) -> list[dict[str, Any]]:
        return [dict(item) for item in self.compacted_history if isinstance(item, dict)]


def is_live_nova_followup(*, requested_mode: str, running: bool) -> bool:
    """True when a new Nova message should join the in-flight loop."""

    return str(requested_mode or "").strip() == "agent" and bool(running)


def should_continue_nova(conversation: NovaConversationState) -> bool:
    """Idle follow-up still has todos/history from the previous Nova run."""

    return bool(conversation.todos or conversation.compacted_history or conversation.last_final_text)


def persist_nova_result(
    conversation: NovaConversationState,
    *,
    todos: list[Any],
    history: list[dict[str, Any]] | None,
    final_text: str = "",
) -> None:
    dumped: list[dict[str, Any]] = []
    for item in todos or []:
        if hasattr(item, "model_dump"):
            dumped.append(dict(item.model_dump()))
        elif isinstance(item, dict):
            dumped.append(dict(item))
    conversation.todos = dumped
    conversation.compacted_history = [dict(row) for row in (history or []) if isinstance(row, dict)]
    conversation.last_final_text = str(final_text or "")
    conversation.running = False
