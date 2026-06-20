from __future__ import annotations

from typing import Any, Protocol


class StudioServerAccessProvider(Protocol):
    def list_owned_server_payloads(self, user: Any) -> list[dict[str, Any]]: ...

    def list_owned_server_ids(
        self,
        user: Any,
        *,
        limit: int | None = None,
        server_type: str | None = None,
        order_by: str = "id",
    ) -> list[int]: ...

    def get_owned_servers_by_ids(
        self,
        user: Any,
        server_ids: list[int] | None,
        *,
        order_by: str = "name",
    ) -> list[Any]: ...

    def get_owned_server(self, user: Any, server_id: int | None) -> Any | None: ...

    def get_owned_server_id_set(self, user: Any, server_ids: list[int] | None) -> set[int]: ...

    def get_first_owned_server_id(
        self,
        user: Any,
        *,
        server_type: str | None = None,
        order_by: str = "id",
    ) -> int | None: ...

    def get_preferred_owned_server_id(
        self,
        user: Any,
        *,
        preferred_name: str | None = None,
        server_type: str | None = None,
        fallback_order_by: str = "name",
    ) -> int | None: ...

    def get_owned_server_name(self, user: Any, server_id: int, *, fallback: str | None = None) -> str: ...

    def has_owned_server(self, user: Any, server_id: int | None, *, server_type: str | None = None) -> bool: ...


_studio_server_access_provider: StudioServerAccessProvider | None = None


def register_studio_server_access_provider(provider: StudioServerAccessProvider | None) -> None:
    global _studio_server_access_provider
    _studio_server_access_provider = provider


def _require_studio_server_access_provider() -> StudioServerAccessProvider:
    if _studio_server_access_provider is None:
        raise RuntimeError("Studio server access provider is not registered")
    return _studio_server_access_provider


def list_owned_server_payloads(user: Any) -> list[dict[str, Any]]:
    return _require_studio_server_access_provider().list_owned_server_payloads(user)


def list_owned_server_ids(
    user: Any,
    *,
    limit: int | None = None,
    server_type: str | None = None,
    order_by: str = "id",
) -> list[int]:
    return _require_studio_server_access_provider().list_owned_server_ids(
        user,
        limit=limit,
        server_type=server_type,
        order_by=order_by,
    )


def get_owned_servers_by_ids(user: Any, server_ids: list[int] | None, *, order_by: str = "name") -> list[Any]:
    return _require_studio_server_access_provider().get_owned_servers_by_ids(
        user,
        server_ids,
        order_by=order_by,
    )


def get_owned_server(user: Any, server_id: int | None) -> Any | None:
    return _require_studio_server_access_provider().get_owned_server(user, server_id)


def get_owned_server_id_set(user: Any, server_ids: list[int] | None) -> set[int]:
    return _require_studio_server_access_provider().get_owned_server_id_set(user, server_ids)


def get_first_owned_server_id(
    user: Any,
    *,
    server_type: str | None = None,
    order_by: str = "id",
) -> int | None:
    return _require_studio_server_access_provider().get_first_owned_server_id(
        user,
        server_type=server_type,
        order_by=order_by,
    )


def get_preferred_owned_server_id(
    user: Any,
    *,
    preferred_name: str | None = None,
    server_type: str | None = None,
    fallback_order_by: str = "name",
) -> int | None:
    return _require_studio_server_access_provider().get_preferred_owned_server_id(
        user,
        preferred_name=preferred_name,
        server_type=server_type,
        fallback_order_by=fallback_order_by,
    )


def get_owned_server_name(user: Any, server_id: int, *, fallback: str | None = None) -> str:
    return _require_studio_server_access_provider().get_owned_server_name(user, server_id, fallback=fallback)


def has_owned_server(user: Any, server_id: int | None, *, server_type: str | None = None) -> bool:
    return _require_studio_server_access_provider().has_owned_server(
        user,
        server_id,
        server_type=server_type,
    )
