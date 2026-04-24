"""
Server-level AI policy checks (2.11).

These helpers query Django models to enforce per-server AI restrictions
such as read-only mode.  They are intentionally separate from
:mod:`servers.services.terminal_ai.policy` (which is pure-Python and
command-level) so the two concerns stay cleanly separated.

Public API
----------
- :func:`is_server_ai_read_only` — sync predicate used from the consumer.
"""
from __future__ import annotations


def is_server_ai_read_only(server_id: int) -> bool:
    """Return ``True`` if the server has ``ai_read_only=True``.

    Fetches only the ``ai_read_only`` column so the call is cheap.
    Returns ``False`` for unknown server IDs (safe default).
    """
    from servers.models import Server

    return bool(
        Server.objects.filter(pk=server_id).values_list("ai_read_only", flat=True).first()
    )
