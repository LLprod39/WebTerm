"""
servers/services/server_query.py

Public API for server retrieval — the canonical way for other bounded contexts
to access Server objects without importing servers.views directly.

Usage:
    from servers.services.server_query import get_server, get_servers_for_user

studio/ and core_ui/ MUST use these functions instead of querying Server ORM directly.
"""
from __future__ import annotations

from django.db.models import Q
from django.utils import timezone

from servers.models import Server, ServerShare

CAPABILITY_VIEW = "view"
CAPABILITY_CONNECT_TERMINAL = "connect_terminal"
CAPABILITY_EXECUTE_COMMAND = "execute_command"
CAPABILITY_READ_FILES = "read_files"
CAPABILITY_WRITE_FILES = "write_files"
CAPABILITY_USE_RDP = "use_rdp"
CAPABILITY_VIEW_CONTEXT = "view_context"
CAPABILITY_ADMIN_SHARE = "admin_share"

_SHARE_CAPABILITY_FIELDS = {
    CAPABILITY_CONNECT_TERMINAL: "can_connect_terminal",
    CAPABILITY_EXECUTE_COMMAND: "can_execute_command",
    CAPABILITY_READ_FILES: "can_read_files",
    CAPABILITY_WRITE_FILES: "can_write_files",
    CAPABILITY_USE_RDP: "can_use_rdp",
}


def get_servers_for_user(user) -> "QuerySet[Server]":
    """
    Return all active servers accessible by the given user
    (own servers + shared servers with active non-revoked shares).
    This is the canonical queryset used across the platform.
    """
    now = timezone.now()
    share_q = (
        Q(shares__user=user, shares__is_revoked=False)
        & (Q(shares__expires_at__isnull=True) | Q(shares__expires_at__gt=now))
    )
    return (
        Server.objects.select_related("group", "user")
        .filter(is_active=True)
        .filter(Q(user=user) | share_q)
        .distinct()
    )


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
        return Server.objects.get(pk=server_id, user=user, is_active=True)
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
