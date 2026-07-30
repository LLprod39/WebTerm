"""Server inventory adapter for the isolated agent command runtime."""

from __future__ import annotations

from typing import Any

from app.agent_kernel.sandbox.ephemeral_runner import AgentCommandResult, execute_ephemeral_ssh_command
from servers.services.ssh_connection import get_server_connect_kwargs
from servers.ssh_host_keys import get_server_trusted_host_keys


def _known_hosts_text(server: Any, connect_kwargs: dict[str, Any]) -> str:
    host = str(connect_kwargs.get("host") or getattr(server, "host", "") or "").strip().strip("[]")
    port = int(connect_kwargs.get("port") or getattr(server, "port", 22) or 22)
    patterns = [f"[{host}]:{port}"]
    if port == 22:
        patterns.insert(0, host)
    return "".join(
        f"{pattern} {record['public_key']}\n"
        for record in get_server_trusted_host_keys(server)
        if record.get("public_key")
        for pattern in patterns
    )


async def run_agent_command(
    server: Any,
    command: str,
    *,
    connect_kwargs: dict[str, Any] | None = None,
    input_text: str | None = None,
    timeout_seconds: int | None = None,
) -> AgentCommandResult:
    resolved_connect_kwargs = connect_kwargs or await get_server_connect_kwargs(server)
    key_path = ""
    if str(getattr(server, "auth_method", "") or "") in {"key", "key_password"}:
        key_path = str(getattr(server, "key_path", "") or "").strip()
    return await execute_ephemeral_ssh_command(
        connect_kwargs=resolved_connect_kwargs,
        command=command,
        known_hosts_text=_known_hosts_text(server, resolved_connect_kwargs),
        key_path=key_path,
        input_text=input_text,
        timeout_seconds=timeout_seconds,
    )
