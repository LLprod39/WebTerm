from __future__ import annotations

from typing import Any

from servers.services.server_query import get_owned_server as get_owned_server_for_user
from servers.services.server_query import get_servers_for_user


class DjangoStudioServerAccessProvider:
    def _owned_servers_queryset(self, user: Any, *, server_type: str | None = None, order_by: str = "name"):
        queryset = get_servers_for_user(user).filter(user=user)
        if server_type:
            queryset = queryset.filter(server_type=server_type)
        return queryset.order_by(order_by)

    def list_owned_server_payloads(self, user: Any) -> list[dict[str, Any]]:
        return [
            {
                "id": server.pk,
                "name": server.name,
                "host": server.host,
            }
            for server in self._owned_servers_queryset(user)
        ]

    def list_owned_server_ids(
        self,
        user: Any,
        *,
        limit: int | None = None,
        server_type: str | None = None,
        order_by: str = "id",
    ) -> list[int]:
        queryset = self._owned_servers_queryset(user, server_type=server_type, order_by=order_by)
        if limit is not None:
            queryset = queryset[:limit]
        return list(queryset.values_list("id", flat=True))

    def get_owned_servers_by_ids(self, user: Any, server_ids: list[int] | None, *, order_by: str = "name") -> list[Any]:
        requested_ids = server_ids or []
        if not requested_ids:
            return []
        return list(self._owned_servers_queryset(user, order_by=order_by).filter(pk__in=requested_ids))

    def get_owned_server(self, user: Any, server_id: int | None) -> Any | None:
        if server_id is None:
            return None
        return get_owned_server_for_user(server_id, user)

    def get_owned_server_id_set(self, user: Any, server_ids: list[int] | None) -> set[int]:
        requested_ids = server_ids or []
        if not requested_ids:
            return set()
        return set(self._owned_servers_queryset(user).filter(pk__in=requested_ids).values_list("id", flat=True))

    def get_first_owned_server_id(
        self,
        user: Any,
        *,
        server_type: str | None = None,
        order_by: str = "id",
    ) -> int | None:
        return (
            self._owned_servers_queryset(user, server_type=server_type, order_by=order_by)
            .values_list("id", flat=True)
            .first()
        )

    def get_preferred_owned_server_id(
        self,
        user: Any,
        *,
        preferred_name: str | None = None,
        server_type: str | None = None,
        fallback_order_by: str = "name",
    ) -> int | None:
        queryset = self._owned_servers_queryset(user, server_type=server_type, order_by=fallback_order_by)
        preferred = str(preferred_name or "").strip()
        if preferred:
            preferred_id = queryset.filter(name=preferred).values_list("id", flat=True).first()
            if preferred_id:
                return int(preferred_id)
        fallback_id = queryset.values_list("id", flat=True).first()
        return int(fallback_id) if fallback_id else None

    def get_owned_server_name(self, user: Any, server_id: int, *, fallback: str | None = None) -> str:
        name = (
            self._owned_servers_queryset(user, order_by="name")
            .filter(pk=server_id)
            .values_list("name", flat=True)
            .first()
        )
        if name:
            return str(name)
        return fallback or f"server-{server_id}"

    def has_owned_server(self, user: Any, server_id: int | None, *, server_type: str | None = None) -> bool:
        if server_id is None:
            return False
        return self._owned_servers_queryset(user, server_type=server_type).filter(pk=server_id).exists()
