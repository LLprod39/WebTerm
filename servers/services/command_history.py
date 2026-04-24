"""
Service for querying command history suggestions (autocomplete overlay).
"""

from __future__ import annotations

from typing import Any

from servers.models import ServerCommandHistory


def save_command_history_entry(
    *,
    server_id: int,
    user_id: int | None,
    command: str,
    output: str = "",
    exit_code: int | None = None,
    session_id: str = "",
    cwd: str = "",
    actor_kind: str = ServerCommandHistory.ACTOR_HUMAN,
    source_kind: str = ServerCommandHistory.SOURCE_TERMINAL,
) -> None:
    """Persist a command history row using the canonical servers service layer."""
    ServerCommandHistory.objects.create(
        server_id=server_id,
        user_id=user_id,
        actor_kind=actor_kind,
        source_kind=source_kind,
        session_id=str(session_id or "")[:120],
        cwd=str(cwd or "")[:500],
        command=command,
        output=(output or "")[:10000],
        exit_code=exit_code,
    )


def get_command_suggestions(
    user,
    server_id: int,
    prefix: str,
    limit: int = 20,
) -> list[str]:
    """Return distinct recent commands matching *prefix* for a server."""
    if not prefix or len(prefix) < 2:
        return []

    cap = max(1, min(limit, 50))
    rows = (
        ServerCommandHistory.objects.filter(
            server_id=server_id,
            actor_kind=ServerCommandHistory.ACTOR_HUMAN,
            command__istartswith=prefix,
        )
        .order_by("-executed_at")
        .values_list("command", flat=True)[: cap * 5]
    )
    seen: set[str] = set()
    result: list[str] = []
    for cmd in rows:
        key = cmd.strip()
        if key in seen:
            continue
        seen.add(key)
        result.append(key)
        if len(result) >= cap:
            break
    return result


def get_recent_session_command_activity(
    *,
    server_id: int,
    session_id: str = "",
    limit: int = 8,
) -> list[dict[str, Any]]:
    cap = max(1, min(limit, 20))
    rows = ServerCommandHistory.objects.filter(
        server_id=server_id,
        actor_kind=ServerCommandHistory.ACTOR_HUMAN,
        source_kind=ServerCommandHistory.SOURCE_TERMINAL,
    )
    normalized_session_id = str(session_id or "").strip()
    if normalized_session_id:
        rows = rows.filter(session_id=normalized_session_id)

    result: list[dict[str, Any]] = []
    for row in rows.order_by("-executed_at").values("command", "cwd", "exit_code")[:cap]:
        result.append(
            {
                "command": str(row.get("command") or ""),
                "cwd": str(row.get("cwd") or ""),
                "exit_code": row.get("exit_code"),
                "source": "history",
            }
        )
    return result
