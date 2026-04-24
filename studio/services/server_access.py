from __future__ import annotations

from typing import Any

from servers.services.server_query import get_servers_for_user


def _owned_servers_queryset(user, *, server_type: str | None = None, order_by: str = "name"):
    qs = get_servers_for_user(user).filter(user=user)
    if server_type:
        qs = qs.filter(server_type=server_type)
    return qs.order_by(order_by)


def list_owned_server_payloads(user) -> list[dict[str, Any]]:
    return [
        {
            "id": server.pk,
            "name": server.name,
            "host": server.host,
        }
        for server in _owned_servers_queryset(user)
    ]


def list_owned_server_ids(
    user,
    *,
    limit: int | None = None,
    server_type: str | None = None,
    order_by: str = "id",
) -> list[int]:
    qs = _owned_servers_queryset(user, server_type=server_type, order_by=order_by)
    if limit is not None:
        qs = qs[:limit]
    return list(qs.values_list("id", flat=True))


def get_owned_servers_by_ids(user, server_ids: list[int] | None, *, order_by: str = "name") -> list[Any]:
    requested_ids = server_ids or []
    if not requested_ids:
        return []
    return list(_owned_servers_queryset(user, order_by=order_by).filter(pk__in=requested_ids))


def get_owned_server(user, server_id: int | None):
    if server_id is None:
        return None
    return _owned_servers_queryset(user, order_by="-updated_at").filter(pk=server_id).first()


def get_owned_server_id_set(user, server_ids: list[int] | None) -> set[int]:
    requested_ids = server_ids or []
    if not requested_ids:
        return set()
    return set(_owned_servers_queryset(user).filter(pk__in=requested_ids).values_list("id", flat=True))


def get_first_owned_server_id(
    user,
    *,
    server_type: str | None = None,
    order_by: str = "id",
) -> int | None:
    return _owned_servers_queryset(user, server_type=server_type, order_by=order_by).values_list("id", flat=True).first()


def get_preferred_owned_server_id(
    user,
    *,
    preferred_name: str | None = None,
    server_type: str | None = None,
    fallback_order_by: str = "name",
) -> int | None:
    qs = _owned_servers_queryset(user, server_type=server_type, order_by=fallback_order_by)
    preferred = str(preferred_name or "").strip()
    if preferred:
        preferred_id = qs.filter(name=preferred).values_list("id", flat=True).first()
        if preferred_id:
            return int(preferred_id)
    fallback_id = qs.values_list("id", flat=True).first()
    return int(fallback_id) if fallback_id else None


def get_owned_server_name(user, server_id: int, *, fallback: str | None = None) -> str:
    name = _owned_servers_queryset(user, order_by="name").filter(pk=server_id).values_list("name", flat=True).first()
    if name:
        return str(name)
    return fallback or f"server-{server_id}"


def has_owned_server(user, server_id: int | None, *, server_type: str | None = None) -> bool:
    if server_id is None:
        return False
    return _owned_servers_queryset(user, server_type=server_type).filter(pk=server_id).exists()
