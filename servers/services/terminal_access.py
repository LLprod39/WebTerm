"""
Terminal access and secret lookup helpers.

Keeps user capability checks, terminal-open ACL lookup, runtime limits, and
server secret resolution out of the Channels consumer.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from channels.db import database_sync_to_async
from django.conf import settings
from django.db.models import Q
from django.utils import timezone

ACTIVE_TERMINAL_CONNECTION_STATUSES = ["connected"]


def _limit_value(name: str) -> int:
    raw = int(getattr(settings, name, 0) or 0)
    return max(raw, 0)


def _limit_error(*, code: str, message: str, limit: int, active: int, scope: str) -> dict[str, object]:
    return {
        "success": False,
        "error": message,
        "code": code,
        "limit": limit,
        "active": active,
        "scope": scope,
    }


def cleanup_stale_terminal_sessions_sync() -> int:
    from servers.models import ServerConnection

    stale_seconds = _limit_value("SSH_TERMINAL_SESSION_STALE_SECONDS")
    if stale_seconds <= 0:
        return 0

    now = timezone.now()
    cutoff = now - timedelta(seconds=stale_seconds)
    return ServerConnection.objects.filter(
        status__in=ACTIVE_TERMINAL_CONNECTION_STATUSES,
        disconnected_at__isnull=True,
        last_seen_at__lt=cutoff,
    ).update(
        status="disconnected",
        disconnected_at=now,
    )


def _active_terminal_connections_queryset():
    from servers.models import ServerConnection

    queryset = ServerConnection.objects.filter(
        status__in=ACTIVE_TERMINAL_CONNECTION_STATUSES,
        disconnected_at__isnull=True,
    )
    stale_seconds = _limit_value("SSH_TERMINAL_SESSION_STALE_SECONDS")
    if stale_seconds <= 0:
        return queryset

    cutoff = timezone.now() - timedelta(seconds=stale_seconds)
    return queryset.filter(last_seen_at__gte=cutoff)


def user_can_servers_sync(user_id: int) -> bool:
    from django.contrib.auth.models import User

    from core_ui.context_processors import user_can_feature

    user = User.objects.filter(id=user_id).first()
    return bool(user and user_can_feature(user, "servers"))


user_can_servers = database_sync_to_async(user_can_servers_sync)


def get_terminal_session_limit_sync(user_id: int) -> dict[str, object] | None:
    from django.contrib.auth.models import User

    user = User.objects.filter(id=user_id).first()
    cleanup_stale_terminal_sessions_sync()
    active_queryset = _active_terminal_connections_queryset()

    if user is not None:
        per_user_limit = _limit_value("SSH_TERMINAL_SESSIONS_PER_USER_LIMIT")
        if per_user_limit:
            active_for_user = active_queryset.filter(user=user).count()
            if active_for_user >= per_user_limit:
                return _limit_error(
                    code="terminal_user_limit_reached",
                    message=f"Too many active terminal sessions for this user (limit {per_user_limit})",
                    limit=per_user_limit,
                    active=active_for_user,
                    scope="user",
                )

    global_limit = _limit_value("SSH_TERMINAL_SESSIONS_GLOBAL_LIMIT")
    if global_limit:
        active_global = active_queryset.count()
        if active_global >= global_limit:
            return _limit_error(
                code="terminal_global_limit_reached",
                message=f"Too many active terminal sessions globally (limit {global_limit})",
                limit=global_limit,
                active=active_global,
                scope="global",
            )

    return None


get_terminal_session_limit = database_sync_to_async(get_terminal_session_limit_sync)


def get_terminal_server_sync(*, user_id: int, server_id: int) -> Any:
    from servers.models import Server

    now = timezone.now()
    return (
        Server.objects.select_related("group", "user")
        .filter(id=server_id, is_active=True)
        .filter(
            Q(user_id=user_id)
            | (
                Q(shares__user_id=user_id, shares__is_revoked=False)
                & (Q(shares__expires_at__isnull=True) | Q(shares__expires_at__gt=now))
            )
        )
        .distinct()
        .get()
    )


get_terminal_server = database_sync_to_async(get_terminal_server_sync)


def resolve_server_secret_sync(*, server_id: int, master_password: str, plain_password: str) -> str:
    from servers.models import Server
    from servers.secret_utils import get_server_auth_secret

    server = Server.objects.only("id", "encrypted_password", "salt", "auth_method").get(id=server_id)
    if server.auth_method not in ("password", "key_password"):
        return ""
    return get_server_auth_secret(
        server,
        master_password=(master_password or "").strip(),
        fallback_plain=plain_password or "",
    )


resolve_server_secret = database_sync_to_async(resolve_server_secret_sync)
