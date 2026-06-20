from __future__ import annotations

from typing import Any

from servers.services.ssh_connection import get_server_connect_kwargs, get_server_sudo_password


class DjangoPipelineSshProvider:
    async def get_server_connect_kwargs(self, server: Any, *, connect_timeout: int | None = None) -> dict[str, Any]:
        return await get_server_connect_kwargs(server, connect_timeout=connect_timeout)

    def get_server_sudo_password(self, server: Any) -> str:
        return get_server_sudo_password(server)
