from __future__ import annotations

from typing import Any

from servers.monitor import _build_connect_kwargs


async def get_server_connect_kwargs(server, *, connect_timeout: int | None = None) -> dict[str, Any]:
    connect_kwargs = dict(await _build_connect_kwargs(server))
    if connect_timeout is not None:
        connect_kwargs["connect_timeout"] = max(1, int(connect_timeout))
    return connect_kwargs
