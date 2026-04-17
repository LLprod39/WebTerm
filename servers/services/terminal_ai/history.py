"""
Persistent terminal AI chat history service (F2-9).

Stores user/assistant turns in ``TerminalAiChatMessage`` so conversation
context survives WebSocket reconnects, page reloads, and server restarts.

Public API (both sync and async flavours):

- :func:`append_message_sync` / :func:`append_message`
- :func:`load_recent_sync` / :func:`load_recent`
- :func:`clear_history_sync` / :func:`clear_history`

The service enforces a rolling window so the ``terminal_ai_messages``
table stays small: once a conversation exceeds ``max_entries`` rows the
oldest entries are hard-deleted in a single follow-up query.
"""
from __future__ import annotations

from typing import Any

from channels.db import database_sync_to_async

MAX_TEXT_LEN = 4000
"""Hard cap on stored text length — keeps payloads sane and predictable."""


def append_message_sync(
    *,
    user_id: int,
    server_id: int,
    role: str,
    text: str,
    max_entries: int = 120,
) -> dict[str, Any]:
    """Persist one chat turn. Trims old rows past ``max_entries``.

    Returns ``{"stored": <bool>, "pruned": <int>}``.
    """
    from servers.models import TerminalAiChatMessage

    cleaned_role = (role or "").strip().lower()
    if cleaned_role not in {"user", "assistant"}:
        return {"stored": False, "pruned": 0}

    cleaned_text = str(text or "").strip()
    if not cleaned_text:
        return {"stored": False, "pruned": 0}
    cleaned_text = cleaned_text[:MAX_TEXT_LEN]

    TerminalAiChatMessage.objects.create(
        user_id=int(user_id),
        server_id=int(server_id),
        role=cleaned_role,
        text=cleaned_text,
    )

    pruned = 0
    if max_entries and max_entries > 0:
        # Find the cutoff id: keep newest ``max_entries`` rows, delete older.
        qs = TerminalAiChatMessage.objects.filter(user_id=user_id, server_id=server_id)
        total = qs.count()
        if total > max_entries:
            # ids of rows to keep (newest first)
            keep_ids = list(
                qs.order_by("-created_at").values_list("id", flat=True)[:max_entries]
            )
            deleted, _ = qs.exclude(id__in=keep_ids).delete()
            pruned = int(deleted or 0)

    return {"stored": True, "pruned": pruned}


def load_recent_sync(
    *,
    user_id: int,
    server_id: int,
    limit: int = 30,
) -> list[dict[str, Any]]:
    """Return the ``limit`` most recent messages in chronological order.

    Shape matches the in-memory ``_ai_history`` format expected by the
    planner prompt: ``[{"role": "user" | "assistant", "text": "..."}]``.
    """
    from servers.models import TerminalAiChatMessage

    if limit <= 0:
        return []

    qs = (
        TerminalAiChatMessage.objects.filter(user_id=user_id, server_id=server_id)
        .order_by("-created_at")
        .values("role", "text")[:limit]
    )
    rows = list(qs)
    # Return oldest → newest so prompt keeps chronological order.
    rows.reverse()
    return [{"role": r["role"], "text": r["text"]} for r in rows]


def clear_history_sync(*, user_id: int, server_id: int) -> int:
    """Wipe the entire terminal-AI chat history for (user, server)."""
    from servers.models import TerminalAiChatMessage

    deleted, _ = TerminalAiChatMessage.objects.filter(
        user_id=user_id, server_id=server_id
    ).delete()
    return int(deleted or 0)


# --- async wrappers --------------------------------------------------------

append_message = database_sync_to_async(append_message_sync)
load_recent = database_sync_to_async(load_recent_sync)
clear_history = database_sync_to_async(clear_history_sync)
