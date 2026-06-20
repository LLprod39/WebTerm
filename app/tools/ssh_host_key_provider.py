from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

KnownHostsProvider = Callable[[Any], Awaitable[Any]]
TofuKnownHostsProvider = Callable[..., Awaitable[tuple[Any, dict[str, str]]]]
HostPortParser = Callable[[str, int], tuple[str, int]]

_ensure_server_known_hosts_provider: KnownHostsProvider | None = None
_tofu_known_hosts_provider: TofuKnownHostsProvider | None = None
_host_port_parser: HostPortParser | None = None


def register_ssh_host_key_provider(
    *,
    ensure_server_known_hosts: KnownHostsProvider | None = None,
    tofu_known_hosts_for_host: TofuKnownHostsProvider | None = None,
    parse_host_port_value: HostPortParser | None = None,
) -> None:
    """Register server-owned SSH host-key verification helpers for app tools."""
    global _ensure_server_known_hosts_provider, _tofu_known_hosts_provider, _host_port_parser
    _ensure_server_known_hosts_provider = ensure_server_known_hosts
    _tofu_known_hosts_provider = tofu_known_hosts_for_host
    _host_port_parser = parse_host_port_value


def parse_host_port_value(host_value: str, default_port: int = 22) -> tuple[str, int]:
    if _host_port_parser is not None:
        return _host_port_parser(host_value, default_port)

    raw = (host_value or "").strip()
    if raw.startswith("["):
        bracket_end = raw.find("]")
        host = raw[1:bracket_end] if bracket_end != -1 else raw.strip("[]")
        remainder = raw[bracket_end + 1 :] if bracket_end != -1 else ""
        port_str = remainder[1:] if remainder.startswith(":") else ""
    elif raw.count(":") == 1:
        host, port_str = raw.rsplit(":", 1)
    else:
        host, port_str = raw, ""

    port = int(port_str) if str(port_str).isdigit() else int(default_port or 22)
    return host.strip(), port


async def ensure_server_known_hosts(server: Any, *, refresh: bool = False) -> Any:
    if _ensure_server_known_hosts_provider is None:
        raise RuntimeError("SSH host-key provider is not registered")
    return await _ensure_server_known_hosts_provider(server, refresh=refresh)


async def tofu_known_hosts_for_host(
    host: str,
    port: int,
    *,
    network_config: Any = None,
    connect_timeout: int = 10,
) -> tuple[Any, dict[str, str]]:
    if _tofu_known_hosts_provider is None:
        raise RuntimeError("SSH host-key provider is not registered")
    return await _tofu_known_hosts_provider(
        host,
        port,
        network_config=network_config,
        connect_timeout=connect_timeout,
    )
