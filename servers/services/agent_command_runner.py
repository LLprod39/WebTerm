"""Server inventory adapter for the isolated agent command runtime."""

from __future__ import annotations

import time
from typing import Any

from opentelemetry.trace import SpanKind, Status, StatusCode

from app.agent_kernel.sandbox.ephemeral_runner import AgentCommandResult, execute_ephemeral_ssh_command
from app.observability import record_ssh_command, start_span
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
                key_path=key_path,
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
