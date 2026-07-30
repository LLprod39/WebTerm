"""Shared helpers for the operator-tools submodules (F-08a split).

``_int_arg`` and ``_server_for_user`` are used by the inventory, monitoring and
action tool modules, so they live here to avoid cross-module cycles.
"""

from __future__ import annotations

from app.assistant_actions import AssistantActionContext, AssistantActionError
from servers.views.server_helpers import _accessible_servers_queryset


def _int_arg(ctx: AssistantActionContext, key: str, *, required: bool = True) -> int | None:
    value = ctx.input_payload.get(key)
    if value is None or value == "":
        if required:
            raise AssistantActionError(f"{key} is required")
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise AssistantActionError(f"{key} must be an integer") from exc
    if parsed <= 0:
        raise AssistantActionError(f"{key} must be positive")
    return parsed


def _server_for_user(user, server_id: int):
    server = _accessible_servers_queryset(user).filter(pk=server_id).first()
    if server is None:
        raise AssistantActionError("Server not found or not accessible", status=404)
    return server
