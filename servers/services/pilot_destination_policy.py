"""Deployment-enforced SSH destination isolation for the closed pilot."""

from __future__ import annotations

import ipaddress
import os
import re
import socket
from collections.abc import Callable
from typing import Any
from urllib.parse import urlsplit


class PilotDestinationDenied(ValueError):
    pass


class PilotDestinationInvalid(ValueError):
    pass


_ALWAYS_DENIED_HOSTS = frozenset(
    {
        "localhost",
        "metadata",
        "metadata.google.internal",
        "postgres",
        "postgresql",
        "redis",
        "backend",
        "web",
        "db",
        "host.docker.internal",
    }
)
_ALWAYS_DENIED_NETWORKS = tuple(
    ipaddress.ip_network(value)
    for value in (
        "0.0.0.0/8",
        "127.0.0.0/8",
        "169.254.0.0/16",
        "224.0.0.0/4",
        "::/128",
        "::1/128",
        "fe80::/10",
        "ff00::/8",
    )
)
_HOSTNAME_RE = re.compile(
    r"(?=.{1,253}\Z)(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)*"
    r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\Z"
)


def pilot_restricted_mode_enabled() -> bool:
    return os.getenv("PILOT_RESTRICTED_MODE", "").strip().lower() in {"1", "true", "yes"}


def _csv(name: str) -> list[str]:
    return [item.strip() for item in os.getenv(name, "").split(",") if item.strip()]


def _allowed_ports() -> set[int]:
    raw = _csv("PILOT_SSH_ALLOWED_PORTS") or ["22", "2222"]
    ports: set[int] = set()
    for value in raw:
        try:
            port = int(value)
        except ValueError as exc:
            raise PilotDestinationDenied("PILOT_SSH_ALLOWED_PORTS contains an invalid port") from exc
        if port < 1 or port > 65535:
            raise PilotDestinationDenied("PILOT_SSH_ALLOWED_PORTS contains an invalid port")
        ports.add(port)
    return ports


def _allowed_networks() -> tuple[ipaddress.IPv4Network | ipaddress.IPv6Network, ...]:
    networks = []
    for value in _csv("PILOT_SSH_ALLOWED_CIDRS"):
        try:
            networks.append(ipaddress.ip_network(value, strict=True))
        except ValueError as exc:
            raise PilotDestinationDenied("PILOT_SSH_ALLOWED_CIDRS contains an invalid CIDR") from exc
    return tuple(networks)


def _resolved_addresses(
    host: str,
    port: int,
    *,
    resolver: Callable[..., list[tuple]] = socket.getaddrinfo,
) -> set[ipaddress.IPv4Address | ipaddress.IPv6Address]:
    try:
        return {ipaddress.ip_address(item[4][0]) for item in resolver(host, port, type=socket.SOCK_STREAM)}
    except (OSError, ValueError) as exc:
        raise PilotDestinationDenied("SSH destination could not be resolved") from exc


def parse_ssh_endpoint(value: Any, *, default_port: int = 22) -> tuple[str, int]:
    """Parse a host or host:port without URL/userinfo ambiguity."""

    if not isinstance(value, str):
        raise PilotDestinationInvalid("SSH tunnel endpoint must be a string")
    raw = value.strip()
    if not raw or any(char.isspace() or ord(char) < 32 for char in raw):
        raise PilotDestinationInvalid("SSH tunnel endpoint is empty or contains whitespace")
    if any(char in raw for char in ("@", "/", "?", "#", "\\")) or "://" in raw:
        raise PilotDestinationInvalid("SSH tunnel endpoint must not contain URL syntax or userinfo")

    port_value: Any = default_port
    if raw.startswith("["):
        match = re.fullmatch(r"\[([^\[\]]+)\](?::([0-9]+))?", raw)
        if not match:
            raise PilotDestinationInvalid("Bracketed SSH tunnel endpoint is malformed")
        host = match.group(1)
        if match.group(2) is not None:
            port_value = match.group(2)
        try:
            ipaddress.IPv6Address(host)
        except ValueError as exc:
            raise PilotDestinationInvalid("Bracketed SSH tunnel host must be an IPv6 address") from exc
    elif raw.count(":") == 1:
        host, port_text = raw.rsplit(":", 1)
        if not host or not port_text or not port_text.isdigit():
            raise PilotDestinationInvalid("SSH tunnel host:port is malformed")
        port_value = port_text
    elif ":" in raw:
        host = raw
        try:
            ipaddress.IPv6Address(host)
        except ValueError as exc:
            raise PilotDestinationInvalid("IPv6 SSH tunnel endpoints with a port must use brackets") from exc
    else:
        host = raw

    normalized_host = host.rstrip(".").lower()
    if "%" in normalized_host:
        raise PilotDestinationInvalid("Scoped IPv6 SSH tunnel endpoints are not supported")
    try:
        ipaddress.ip_address(normalized_host)
    except ValueError as exc:
        if not _HOSTNAME_RE.fullmatch(normalized_host):
            raise PilotDestinationInvalid("SSH tunnel hostname is malformed") from exc

    try:
        normalized_port = int(port_value)
    except (TypeError, ValueError) as exc:
        raise PilotDestinationInvalid("SSH tunnel port is invalid") from exc
    if normalized_port < 1 or normalized_port > 65535:
        raise PilotDestinationInvalid("SSH tunnel port is invalid")
    return normalized_host, normalized_port


def validate_pilot_network_config(
    network_config: Any,
    *,
    resolver: Callable[..., list[tuple]] = socket.getaddrinfo,
) -> tuple[str, int] | None:
    """Validate the bastion which AsyncSSH will use as its tunnel."""

    if network_config in (None, {}):
        return None
    if not isinstance(network_config, dict):
        raise PilotDestinationInvalid("network_config must be an object")
    network = network_config.get("network") or {}
    if not isinstance(network, dict):
        raise PilotDestinationInvalid("network_config.network must be an object")
    proxy = network_config.get("proxy") or {}
    if not isinstance(proxy, dict):
        raise PilotDestinationInvalid("network_config.proxy must be an object")
    raw_bastion = network.get("bastion_host")
    bastion_endpoint = None
    if raw_bastion not in (None, ""):
        host, port = parse_ssh_endpoint(raw_bastion)
        validate_pilot_ssh_destination(host, port, resolver=resolver)
        bastion_endpoint = (host, port)

    raw_proxy = proxy.get("http_proxy")
    if raw_proxy not in (None, ""):
        if bastion_endpoint:
            raise PilotDestinationInvalid("Configure either an SSH bastion or an HTTP proxy, not both")
        validated_pilot_http_proxy_tunnel(raw_proxy, resolver=resolver)
    return bastion_endpoint


def validated_pilot_network_tunnel(network_config: Any) -> str | None:
    """Return the normalized, policy-approved AsyncSSH tunnel target."""

    endpoint = validate_pilot_network_config(network_config)
    if endpoint is None:
        return None
    host, port = endpoint
    formatted_host = f"[{host}]" if ":" in host else host
    return formatted_host if port == 22 else f"{formatted_host}:{port}"


def validated_pilot_http_proxy_tunnel(
    value: Any,
    *,
    resolver: Callable[..., list[tuple]] = socket.getaddrinfo,
) -> tuple[str, int] | None:
    """Strictly parse and policy-check an HTTP CONNECT proxy endpoint."""

    if value in (None, ""):
        return None
    if not isinstance(value, str):
        raise PilotDestinationInvalid("SSH proxy endpoint must be a string")
    raw = value.strip()
    try:
        parsed = urlsplit(raw)
        port = parsed.port
    except ValueError as exc:
        raise PilotDestinationInvalid("SSH proxy endpoint is malformed") from exc
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        raise PilotDestinationInvalid("SSH proxy endpoint must be an HTTP(S) origin without userinfo")
    normalized_port = port or (443 if parsed.scheme == "https" else 80)
    endpoint_host = f"[{parsed.hostname}]" if ":" in parsed.hostname else parsed.hostname
    host, normalized_port = parse_ssh_endpoint(f"{endpoint_host}:{normalized_port}")
    validate_pilot_ssh_destination(host, normalized_port, resolver=resolver)
    return host, normalized_port


def validate_pilot_ssh_destination(
    host: str,
    port: int,
    *,
    resolver: Callable[..., list[tuple]] = socket.getaddrinfo,
) -> None:
    """Fail closed unless every resolved address belongs to the disposable-host allowlist."""
    if not pilot_restricted_mode_enabled():
        return
    normalized_host = str(host or "").strip().strip("[]").rstrip(".").lower()
    try:
        normalized_port = int(port)
    except (TypeError, ValueError) as exc:
        raise PilotDestinationDenied("SSH destination port is invalid") from exc
    if not normalized_host or normalized_host in _ALWAYS_DENIED_HOSTS:
        raise PilotDestinationDenied("SSH destination is denied by pilot isolation policy")
    if normalized_port not in _allowed_ports():
        raise PilotDestinationDenied("SSH destination port is outside the pilot allowlist")

    allowed_hosts = {value.strip("[]").rstrip(".").lower() for value in _csv("PILOT_SSH_ALLOWED_HOSTS")}
    allowed_networks = _allowed_networks()
    if not allowed_hosts and not allowed_networks:
        raise PilotDestinationDenied("Pilot SSH destination allowlist is empty")

    try:
        literal_address = ipaddress.ip_address(normalized_host)
    except ValueError:
        literal_address = None
    addresses = (
        {literal_address}
        if literal_address is not None
        else _resolved_addresses(
            normalized_host,
            normalized_port,
            resolver=resolver,
        )
    )
    if not addresses:
        raise PilotDestinationDenied("SSH destination resolved to no addresses")
    for address in addresses:
        if any(address in network for network in _ALWAYS_DENIED_NETWORKS):
            raise PilotDestinationDenied("SSH destination resolves to a protected address")

    host_allowed = normalized_host in allowed_hosts
    addresses_allowed = all(
        str(address) in allowed_hosts or any(address in network for network in allowed_networks)
        for address in addresses
    )
    if not host_allowed and literal_address is None:
        raise PilotDestinationDenied("SSH hostname is outside the pilot allowlist")
    if not addresses_allowed:
        raise PilotDestinationDenied("SSH destination address is outside the disposable-host allowlist")
