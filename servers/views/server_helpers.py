"""
Shared server view helpers.

These helpers are intentionally kept out of the legacy `_views_all.py` module so
focused view modules can depend on explicit names.
"""

import os

from django.contrib.auth.models import User
from django.db.models import Q
from django.utils import timezone

from servers.models import Server, ServerGroup, ServerGroupMember, ServerShare
from servers.secret_utils import get_server_auth_secret, get_server_sudo_secret
from servers.services.server_query import can_access_server_context, get_active_share, get_servers_for_user, user_has_server_capability


def _serialize_detected_os_fields(server: Server) -> dict:
    meta = server.detected_os_meta if isinstance(server.detected_os_meta, dict) else {}
    pretty = (meta.get("pretty_name") or "").strip()
    return {
        "detected_os": (server.detected_os or "").strip(),
        "detected_os_pretty": pretty,
        "detected_os_meta": meta,
    }


def _get_group_role(group: ServerGroup, user: User) -> str:
    if group.user_id == user.id:
        return "owner"
    membership = ServerGroupMember.objects.filter(group=group, user=user).first()
    return membership.role if membership else ""


def _active_share_q(user: User) -> Q:
    now = timezone.now()
    return Q(shares__user=user, shares__is_revoked=False) & (
        Q(shares__expires_at__isnull=True) | Q(shares__expires_at__gt=now)
    )


def _accessible_servers_queryset(user: User):
    return get_servers_for_user(user)


def _active_server_share(server: Server, user: User) -> ServerShare | None:
    return get_active_share(server, user)


def _shared_server_context_allowed(server: Server, user: User, share: ServerShare | None = None) -> bool:
    return can_access_server_context(server, user, share)


def _server_capabilities(server: Server, user: User, share: ServerShare | None = None) -> dict[str, bool]:
    return {
        "view": user_has_server_capability(server, user, "view", share),
        "connect_terminal": user_has_server_capability(server, user, "connect_terminal", share),
        "execute_command": user_has_server_capability(server, user, "execute_command", share),
        "read_files": user_has_server_capability(server, user, "read_files", share),
        "write_files": user_has_server_capability(server, user, "write_files", share),
        "view_context": user_has_server_capability(server, user, "view_context", share),
        "admin_share": user_has_server_capability(server, user, "admin_share", share),
    }


def _server_has_capability(server: Server, user: User, capability: str, share: ServerShare | None = None) -> bool:
    return user_has_server_capability(server, user, capability, share)


def _effective_master_password(request, data: dict | None = None) -> str:
    """Resolve master password from payload, session, or env."""
    data = data or {}
    from_payload = str(data.get("master_password") or "").strip()
    if from_payload:
        return from_payload

    try:
        from_session = str(request.session.get("_mp") or "").strip()
    except Exception:
        from_session = ""
    if from_session:
        return from_session

    return str(os.environ.get("MASTER_PASSWORD") or "").strip()


def _resolve_server_secret(server: Server, request, data: dict) -> str | None:
    """Resolve server password/passphrase from encrypted secret or direct payload."""
    if server.auth_method not in ["password", "key_password"]:
        return None

    direct_secret = str(data.get("password") or "").strip()
    master_password = _effective_master_password(request, data)
    try:
        secret = get_server_auth_secret(
            server,
            master_password=master_password,
            fallback_plain=direct_secret,
        )
    except ValueError as exc:
        raise ValueError("Не удалось расшифровать пароль сервера. Проверь MASTER_PASSWORD в .env.") from exc
    return secret or None


def _resolve_server_sudo_secret(server: Server, request, data: dict) -> str:
    """Resolve stored sudo password without exposing it to agents or logs."""
    if getattr(server, "sudo_auth_mode", "none") != "stored_password":
        return ""

    direct_secret = str(data.get("sudo_password") or "").strip()
    master_password = _effective_master_password(request, data)
    try:
        return get_server_sudo_secret(
            server,
            master_password=master_password,
            fallback_plain=direct_secret,
        )
    except ValueError as exc:
        raise ValueError("Не удалось расшифровать sudo-пароль сервера. Проверь MASTER_PASSWORD в .env.") from exc


def _require_ssh_server(server: Server) -> None:
    if not server.is_ssh():
        raise ValueError("SFTP доступен только для SSH-серверов")
