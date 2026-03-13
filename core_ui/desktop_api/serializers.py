from __future__ import annotations

from datetime import timedelta

from django.db.models import Q
from django.utils import timezone

from core_ui.context_processors import FEATURE_SLUGS, user_can_feature
from core_ui.managed_secrets import get_mcp_secret_env_keys
from servers.models import ServerConnection
from servers.secret_utils import has_saved_server_secret


def serialize_user(user) -> dict:
    return {
        "id": int(user.id),
        "username": user.username,
        "email": user.email or "",
        "is_staff": bool(user.is_staff),
        "features": {feature: bool(user_can_feature(user, feature)) for feature in FEATURE_SLUGS},
    }


def _connected_server_ids(server_ids: list[int]) -> set[int]:
    if not server_ids:
        return set()
    return set(
        ServerConnection.objects.filter(server_id__in=server_ids, status="connected").values_list("server_id", flat=True)
    )


def server_status(server, connected_server_ids: set[int] | None = None) -> str:
    connected_server_ids = connected_server_ids or set()
    now = timezone.now()
    if server.id in connected_server_ids:
        return "online"
    if server.last_connected:
        if now - server.last_connected <= timedelta(minutes=15):
            return "online"
        return "offline"
    return "unknown"


def serialize_group(group) -> dict:
    return {
        "id": int(group.id),
        "name": group.name,
        "description": group.description,
        "color": group.color,
        "server_count": int(getattr(group, "server_count", 0)),
    }


def serialize_server_summary(server, *, connected_server_ids: set[int] | None = None, share=None) -> dict:
    return {
        "id": int(server.id),
        "name": server.name,
        "host": server.host,
        "port": int(server.port or 0),
        "username": server.username,
        "server_type": server.server_type or "ssh",
        "status": server_status(server, connected_server_ids),
        "group_id": server.group_id,
        "group_name": server.group.name if server.group else "Ungrouped",
        "is_shared": bool(share),
        "last_connected": server.last_connected.isoformat() if server.last_connected else None,
    }


def serialize_server_detail(server, *, current_user, share=None, can_access_context: bool = True) -> dict:
    is_owner = bool(server.user_id == current_user.id)
    return {
        "id": int(server.id),
        "name": server.name,
        "host": server.host,
        "port": int(server.port or 0),
        "username": server.username,
        "server_type": server.server_type or "ssh",
        "auth_method": server.auth_method,
        "key_path": server.key_path,
        "tags": server.tags,
        "notes": server.notes if can_access_context else "",
        "corporate_context": server.corporate_context if can_access_context else "",
        "network_config": (server.network_config or {}) if can_access_context else {},
        "group_id": server.group_id,
        "group_name": server.group.name if server.group else "",
        "is_active": bool(server.is_active),
        "has_saved_secret": bool(is_owner and has_saved_server_secret(server)),
        "can_edit": is_owner,
        "is_shared_server": bool(share),
        "share_context_enabled": bool(share.share_context) if share else True,
        "shared_by_username": share.shared_by.username if share and share.shared_by else "",
    }


def serialize_knowledge_item(item) -> dict:
    return {
        "id": int(item.id),
        "title": item.title,
        "content": item.content,
        "category": item.category,
        "category_label": item.get_category_display(),
        "source": item.source,
        "source_label": item.get_source_display(),
        "confidence": float(item.confidence or 0.0),
        "is_active": bool(item.is_active),
        "updated_at": item.updated_at.isoformat() if item.updated_at else None,
    }


def serialize_global_context(rules) -> dict:
    return {
        "rules": rules.rules,
        "forbidden_commands": list(rules.forbidden_commands or []),
        "required_checks": list(rules.required_checks or []),
        "environment_vars": dict(rules.environment_vars or {}),
    }


def serialize_group_context(group, *, include_environment_vars: bool = True) -> dict:
    return {
        "id": int(group.id),
        "name": group.name,
        "rules": group.rules,
        "forbidden_commands": list(group.forbidden_commands or []),
        "environment_vars": dict(group.environment_vars or {}) if include_environment_vars else {},
    }


def serialize_mcp_summary(mcp) -> dict:
    return {
        "id": int(mcp.id),
        "name": mcp.name,
        "description": mcp.description,
        "transport": mcp.transport,
        "command": mcp.command,
        "args": list(mcp.args or []),
        "env": dict(mcp.env or {}),
        "secret_env_keys": get_mcp_secret_env_keys(mcp.id),
        "url": mcp.url,
        "is_shared": bool(mcp.is_shared),
        "last_test_ok": mcp.last_test_ok,
        "last_test_at": mcp.last_test_at.isoformat() if mcp.last_test_at else None,
        "last_test_error": mcp.last_test_error,
    }


def accessible_share_for_server(server, user):
    if not server or server.user_id == user.id:
        return None
    now = timezone.now()
    return (
        server.shares.select_related("shared_by")
        .filter(user=user, is_revoked=False)
        .filter(Q(expires_at__isnull=True) | Q(expires_at__gt=now))
        .first()
    )


def connected_ids_for_servers(servers: list) -> set[int]:
    return _connected_server_ids([server.id for server in servers])
