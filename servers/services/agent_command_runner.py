"""Server inventory adapter for the isolated agent command runtime."""

from __future__ import annotations

import time
from typing import Any

from asgiref.sync import sync_to_async
from django.conf import settings
from opentelemetry.trace import SpanKind, Status, StatusCode

from app.agent_kernel.sandbox.ephemeral_runner import (
    AgentCommandResult,
    agent_command_uses_docker,
    execute_ephemeral_ssh_command,
)
from app.core.docker_host_routing import route_loopback_host
from app.observability import record_ssh_command, start_span
from servers.services.ssh_connection import get_server_connect_kwargs
from servers.ssh_host_keys import get_server_trusted_host_keys
from servers.ssh_private_keys import get_server_private_key_text


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


def _route_for_runner_container(connect_kwargs: dict[str, Any]) -> dict[str, Any]:
    """The runner is its own bridge-network container: loopback is never the target host."""
    if connect_kwargs.get("tunnel"):
        return connect_kwargs
    network = str(getattr(settings, "AGENT_COMMAND_DOCKER_NETWORK", "bridge") or "bridge").strip().lower()
    if network in {"host", "none"}:
        return connect_kwargs
    try:
        uses_docker = agent_command_uses_docker()
    except Exception:  # noqa: BLE001 - runtime errors surface later in execute
        return connect_kwargs
    if not uses_docker:
        return connect_kwargs
    host = str(connect_kwargs.get("host") or "")
    routed = route_loopback_host(host, force=True, purpose="agent-runner SSH")
    if routed == host:
        return connect_kwargs
    return {**connect_kwargs, "host": routed}


async def run_agent_command(
    server: Any,
    command: str,
    *,
    connect_kwargs: dict[str, Any] | None = None,
    input_text: str | None = None,
    timeout_seconds: int | None = None,
) -> AgentCommandResult:
    resolved_connect_kwargs = _route_for_runner_container(connect_kwargs or await get_server_connect_kwargs(server))
    private_key = ""
    if str(getattr(server, "auth_method", "") or "") in {"key", "key_password"}:
        private_key = await sync_to_async(get_server_private_key_text, thread_sensitive=True)(server)
    command_text = str(command or "")
    attributes = {
        "server.id": int(getattr(server, "id", 0) or 0),
        "server.address": str(resolved_connect_kwargs.get("host") or "")[:255],
        "server.port": int(resolved_connect_kwargs.get("port") or 22),
        "command.length": len(command_text),
    }
    started = time.monotonic()
    with start_span("ssh.command", kind=SpanKind.CLIENT, attributes=attributes) as span:
        try:
            result = await execute_ephemeral_ssh_command(
                connect_kwargs=resolved_connect_kwargs,
                command=command_text,
                known_hosts_text=_known_hosts_text(server, resolved_connect_kwargs),
                private_key=private_key,
                input_text=input_text,
                timeout_seconds=timeout_seconds,
            )
        except Exception:
            record_ssh_command(
                duration_ms=(time.monotonic() - started) * 1000,
                success=False,
                runtime="error",
            )
            raise
        success = result.exit_status == 0
        span.set_attribute("ssh.exit_code", result.exit_status)
        span.set_attribute("command.runtime", result.runtime)
        span.set_attribute("command.duration_ms", result.duration_ms)
        if not success:
            span.set_status(Status(StatusCode.ERROR, f"SSH exit code {result.exit_status}"))
        record_ssh_command(duration_ms=result.duration_ms, success=success, runtime=result.runtime)
        return result
