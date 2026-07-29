"""
servers/services/server_query.py

Public API for server retrieval — the canonical way for other bounded contexts
to access Server objects without importing servers.views directly.

Usage:
    from servers.services.server_query import get_server, get_servers_for_user

studio/ and core_ui/ MUST use these functions instead of querying Server ORM directly.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db.models import Q
from django.utils import timezone

from servers.models import Server, ServerShare

if TYPE_CHECKING:
    from django.db.models import QuerySet

CAPABILITY_VIEW = "view"
CAPABILITY_CONNECT_TERMINAL = "connect_terminal"
CAPABILITY_EXECUTE_COMMAND = "execute_command"
CAPABILITY_READ_FILES = "read_files"
CAPABILITY_WRITE_FILES = "write_files"
CAPABILITY_VIEW_CONTEXT = "view_context"
CAPABILITY_ADMIN_SHARE = "admin_share"

_SHARE_CAPABILITY_FIELDS = {
    CAPABILITY_CONNECT_TERMINAL: "can_connect_terminal",
    CAPABILITY_EXECUTE_COMMAND: "can_execute_command",
    CAPABILITY_READ_FILES: "can_read_files",
    CAPABILITY_WRITE_FILES: "can_write_files",
}


def get_servers_for_user(user) -> QuerySet[Server]:
    """
    Return all active servers accessible by the given user
    (own servers + shared servers with active non-revoked shares).
    This is the canonical queryset used across the platform.
    """
    return get_servers_for_user_capability(user, CAPABILITY_VIEW)


def get_servers_for_user_capability(user, capability: str) -> QuerySet[Server]:
    """Return active SSH servers on which ``user`` holds the exact capability."""
    now = timezone.now()
    active_share_q = Q(shares__user=user, shares__is_revoked=False) & (
        Q(shares__expires_at__isnull=True) | Q(shares__expires_at__gt=now)
    )
    if capability == CAPABILITY_VIEW:
        share_q = active_share_q
    elif capability == CAPABILITY_VIEW_CONTEXT:
        share_q = active_share_q & Q(shares__share_context=True)
    else:
        field = _SHARE_CAPABILITY_FIELDS.get(capability)
        share_q = active_share_q & Q(**{f"shares__{field}": True}) if field else Q(pk__in=[])
    return (
        Server.objects.select_related("group", "user")
        .filter(is_active=True)
        .filter(server_type="ssh")
        .filter(Q(user=user) | share_q)
        .distinct()
    )


def resolve_servers_for_user_capability(
    server_ids,
    user,
    capability: str,
    *,
    base_queryset=None,
) -> tuple[list[Server], list[int]]:
    """Resolve requested ids in order and report every id denied by the exact capability."""
    requested: list[int] = []
    for value in server_ids or []:
        try:
            server_id = int(value)
        except (TypeError, ValueError):
            continue
        if server_id > 0 and server_id not in requested:
            requested.append(server_id)
    permitted_ids = get_servers_for_user_capability(user, capability).filter(pk__in=requested).values("pk")
    queryset = base_queryset if base_queryset is not None else Server.objects.all()
    servers_by_id = {server.id: server for server in queryset.filter(pk__in=permitted_ids)}
    resolved = [servers_by_id[server_id] for server_id in requested if server_id in servers_by_id]
    denied = [server_id for server_id in requested if server_id not in servers_by_id]
    return resolved, denied


def get_server(server_id: int, user) -> Server | None:
    """
    Return a single active server accessible by the user, or None.
    """
    return get_servers_for_user(user).filter(pk=server_id).first()


def get_owned_server(server_id: int, user) -> Server | None:
    """
    Return a single active server owned by the user, or None.
    """
    try:
        return Server.objects.get(pk=server_id, user=user, is_active=True, server_type="ssh")
    except (Server.DoesNotExist, TypeError, ValueError):
        return None


def get_active_share(server: Server, user) -> ServerShare | None:
    """
    Return the active ServerShare for a shared server, or None if the user owns it.
    """
    if not server or server.user_id == user.id:
        return None
    now = timezone.now()
    return (
        ServerShare.objects.filter(server=server, user=user, is_revoked=False)
        .filter(Q(expires_at__isnull=True) | Q(expires_at__gt=now))
        .first()
    )


def can_access_server_context(server: Server, user, share: ServerShare | None = None) -> bool:
    """
    Return True if the user may read AI context/memory for this server.
    Own servers always allow context. Shared servers require share_context=True.
    """
    if not server:
        return False
    if server.user_id == user.id:
        return True
    active_share = share if share is not None else get_active_share(server, user)
    return bool(active_share and getattr(active_share, "share_context", False))


def user_has_server_capability(
    server: Server | None,
    user,
    capability: str,
    share: ServerShare | None = None,
) -> bool:
    if not server or not user or not getattr(user, "is_authenticated", True):
        return False
    if server.user_id == user.id:
        return True
    active_share = share if share is not None else get_active_share(server, user)
    if not active_share:
        return False
    if capability == CAPABILITY_VIEW:
        return True
    if capability == CAPABILITY_VIEW_CONTEXT:
        return bool(active_share.share_context)
    field = _SHARE_CAPABILITY_FIELDS.get(capability)
    return bool(field and getattr(active_share, field, False))


def get_server_for_user_capability(server_id: int, user, capability: str) -> Server | None:
    server = get_server(server_id, user)
    if not server:
        return None
    return server if user_has_server_capability(server, user, capability) else None
