"""Fail-closed SSH host-key material for generated Ansible inventories."""

from __future__ import annotations

from typing import Any

from servers.ssh_host_keys import SSHHostKeyVerificationError, get_server_trusted_host_keys


def require_trusted_host_keys(servers: list[Any]) -> dict[int, list[dict[str, str]]]:
    trusted_by_server_id: dict[int, list[dict[str, str]]] = {}
    missing_trust: list[str] = []
    for server in servers:
        trusted_host_keys = get_server_trusted_host_keys(server)
        if not trusted_host_keys:
            missing_trust.append(str(getattr(server, "name", "") or f"server-{server.id}"))
        trusted_by_server_id[int(server.id)] = trusted_host_keys

    if missing_trust:
        names = ", ".join(missing_trust)
        raise SSHHostKeyVerificationError(
            f"Нет подтверждённого SSH host key для Ansible targets: {names}. Сначала проверь fingerprint владельцем."
        )
    return trusted_by_server_id
