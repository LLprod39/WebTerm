"""Compatibility helpers for the retired per-server AI mode."""

from __future__ import annotations


def is_server_ai_read_only(server_id: int) -> bool:
    """Legacy API: interactive AI no longer has a read-only mode."""
    return False


def is_terminal_ai_read_only_for_user(server_id: int, user_id: int | None) -> bool:
    """Legacy API: authorization is enforced by server access and approvals."""
    return False
