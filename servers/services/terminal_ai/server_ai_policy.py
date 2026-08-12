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
    Returns ``True`` for unknown server IDs (fail-closed default).
    """
    from servers.models import Server

    value = Server.objects.filter(pk=server_id).values_list("ai_read_only", flat=True).first()
    return True if value is None else bool(value)


def is_terminal_ai_read_only_for_user(server_id: int, user_id: int | None) -> bool:
    """Recheck both the server boundary and the live automation capability."""
    if is_server_ai_read_only(server_id) or not user_id:
        return True
    from django.contrib.auth import get_user_model

    from servers.agents.agent_pilot_policy import user_can_automate

    user = get_user_model().objects.filter(pk=user_id, is_active=True).first()
    return not bool(user and user_can_automate(user))
