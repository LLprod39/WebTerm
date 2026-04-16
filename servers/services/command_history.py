"""
Service for querying command history suggestions (autocomplete overlay).
"""

from __future__ import annotations

from servers.models import ServerCommandHistory


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
