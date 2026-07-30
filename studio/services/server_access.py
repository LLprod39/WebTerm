from __future__ import annotations

from typing import Any

from app.studio_server_access import (
    get_first_owned_server_id as _get_first_owned_server_id,
)
from app.studio_server_access import (
    get_owned_server as _get_owned_server,
)
from app.studio_server_access import (
    get_owned_server_id_set as _get_owned_server_id_set,
)
from app.studio_server_access import (
    get_owned_server_name as _get_owned_server_name,
)
from app.studio_server_access import (
    get_owned_servers_by_ids as _get_owned_servers_by_ids,
)
from app.studio_server_access import (
    get_preferred_owned_server_id as _get_preferred_owned_server_id,
)
from app.studio_server_access import (
    has_owned_server as _has_owned_server,
)
from app.studio_server_access import (
    list_owned_server_ids as _list_owned_server_ids,
)
from app.studio_server_access import (
    list_owned_server_payloads as _list_owned_server_payloads,
)


def list_owned_server_payloads(user) -> list[dict[str, Any]]:
    return _list_owned_server_payloads(user)


def list_owned_server_ids(
    user,
    *,
    limit: int | None = None,
    server_type: str | None = None,
    order_by: str = "id",
) -> list[int]:
    return _list_owned_server_ids(user, limit=limit, server_type=server_type, order_by=order_by)


def get_owned_servers_by_ids(user, server_ids: list[int] | None, *, order_by: str = "name") -> list[Any]:
    return _get_owned_servers_by_ids(user, server_ids, order_by=order_by)


def get_owned_server(user, server_id: int | None, *, project_id: int | None = None):
    return _get_owned_server(user, server_id, project_id=project_id)


def get_owned_server_id_set(user, server_ids: list[int] | None) -> set[int]:
    return _get_owned_server_id_set(user, server_ids)


def get_first_owned_server_id(
    user,
    *,
    server_type: str | None = None,
    order_by: str = "id",
) -> int | None:
    return _get_first_owned_server_id(user, server_type=server_type, order_by=order_by)


def get_preferred_owned_server_id(
    user,
    *,
    preferred_name: str | None = None,
    server_type: str | None = None,
    fallback_order_by: str = "name",
) -> int | None:
    return _get_preferred_owned_server_id(
        user,
        preferred_name=preferred_name,
        server_type=server_type,
        fallback_order_by=fallback_order_by,
    )


def get_owned_server_name(user, server_id: int, *, fallback: str | None = None) -> str:
    return _get_owned_server_name(user, server_id, fallback=fallback)


def has_owned_server(user, server_id: int | None, *, server_type: str | None = None) -> bool:
    return _has_owned_server(user, server_id, server_type=server_type)
