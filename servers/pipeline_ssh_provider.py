from __future__ import annotations

from typing import Any

from servers.services.agent_command_runner import run_agent_command
from servers.services.ssh_connection import get_server_connect_kwargs, get_server_sudo_password


class DjangoPipelineSshProvider:
    async def get_server_connect_kwargs(self, server: Any, *, connect_timeout: int | None = None) -> dict[str, Any]:
        return await get_server_connect_kwargs(server, connect_timeout=connect_timeout)

    def get_server_sudo_password(self, server: Any) -> str:
        return get_server_sudo_password(server)

    async def run_agent_command(
        self,
        server: Any,
        command: str,
        *,
        connect_kwargs: dict[str, Any] | None = None,
        input_text: str | None = None,
        timeout_seconds: int | None = None,
    ) -> Any:
        return await run_agent_command(
            server,
            command,
            connect_kwargs=connect_kwargs,
            input_text=input_text,
            timeout_seconds=timeout_seconds,
        )
