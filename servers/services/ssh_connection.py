from __future__ import annotations

from typing import Any

from servers.monitoring import monitor
from servers.secret_utils import get_server_sudo_secret


async def get_server_connect_kwargs(server, *, connect_timeout: int | None = None) -> dict[str, Any]:
    connect_kwargs = dict(await monitor._build_connect_kwargs(server))
    if connect_timeout is not None:
        connect_kwargs["connect_timeout"] = max(1, int(connect_timeout))
    return connect_kwargs


def get_server_sudo_password(server) -> str:
    return get_server_sudo_secret(server)
