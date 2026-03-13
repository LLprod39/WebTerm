from __future__ import annotations

import asyncio
from typing import Any

import asyncssh
from asgiref.sync import sync_to_async
from django.utils import timezone

from servers.models import Server


class SSHHostKeyVerificationError(RuntimeError):
    """Raised when the SSH server host key cannot be verified."""


def parse_host_port_value(host_value: str, default_port: int = 22) -> tuple[str, int]:
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


def parse_server_host_port(server: Server) -> tuple[str, int]:
    return parse_host_port_value(server.host or "", int(server.port or 22))


def _network_tunnel(network_config: Any) -> str | None:
    if not isinstance(network_config, dict):
        return None
    bastion = (network_config.get("network") or {}).get("bastion_host")
    if not bastion:
        return None
    return str(bastion).strip() or None


def _normalize_public_key(public_key: str) -> str:
    value = str(public_key or "").strip()
    if not value:
        raise SSHHostKeyVerificationError("Пустой SSH host key")
    return value


def _serialize_host_key(key: asyncssh.SSHKey, *, trusted_at: str | None = None) -> dict[str, str]:
    public_key = key.export_public_key("openssh")
    if isinstance(public_key, bytes):
        public_key = public_key.decode("utf-8")
    return {
        "public_key": _normalize_public_key(public_key),
        "algorithm": str(key.get_algorithm() or "").strip(),
        "fingerprint_sha256": str(key.get_fingerprint("sha256") or "").strip(),
        "trusted_at": trusted_at or timezone.now().isoformat(),
    }


def normalize_trusted_host_keys(raw_value: Any) -> list[dict[str, str]]:
    values = raw_value if isinstance(raw_value, list) else ([raw_value] if raw_value else [])
    normalized: list[dict[str, str]] = []
    seen: set[str] = set()

    for item in values:
        try:
            if isinstance(item, str):
                parsed = asyncssh.import_public_key(_normalize_public_key(item))
                record = _serialize_host_key(parsed)
            elif isinstance(item, dict):
                public_key = _normalize_public_key(item.get("public_key", ""))
                parsed = asyncssh.import_public_key(public_key)
                record = _serialize_host_key(parsed, trusted_at=str(item.get("trusted_at") or "").strip() or None)
                if item.get("algorithm"):
                    record["algorithm"] = str(item["algorithm"]).strip()
                if item.get("fingerprint_sha256"):
                    record["fingerprint_sha256"] = str(item["fingerprint_sha256"]).strip()
            else:
                continue
        except Exception:
            continue

        key_value = record["public_key"]
        if key_value in seen:
            continue
        seen.add(key_value)
        normalized.append(record)

    return normalized


def get_server_trusted_host_keys(server: Server) -> list[dict[str, str]]:
    return normalize_trusted_host_keys(getattr(server, "trusted_host_keys", None))


def has_trusted_host_keys(server: Server) -> bool:
    return bool(get_server_trusted_host_keys(server))


def _known_hosts_host(host: str, port: int) -> str:
    normalized_host = str(host or "").strip().strip("[]")
    return f"[{normalized_host}]:{int(port or 22)}"


def build_known_hosts(host: str, port: int, records: list[dict[str, str]]) -> asyncssh.SSHKnownHosts:
    normalized_host = str(host or "").strip().strip("[]")
    host_patterns = [_known_hosts_host(normalized_host, port)]
    if int(port or 22) == 22:
        host_patterns.insert(0, normalized_host)

    lines = [
        f"{pattern} {record['public_key']}"
        for record in records
        if record.get("public_key")
        for pattern in host_patterns
    ]
    if not lines:
        raise SSHHostKeyVerificationError("Нет trusted SSH host keys для проверки соединения")
    return asyncssh.import_known_hosts("\n".join(lines) + "\n")


def build_known_hosts_for_server(server: Server) -> asyncssh.SSHKnownHosts:
    host, port = parse_server_host_port(server)
    records = get_server_trusted_host_keys(server)
    return build_known_hosts(host, port, records)


def build_server_connect_kwargs(
    server: Server,
    *,
    secret: str = "",
    known_hosts: asyncssh.SSHKnownHosts,
    connect_timeout: int = 10,
    login_timeout: int = 15,
    keepalive_interval: int | None = None,
    keepalive_count_max: int | None = None,
) -> dict[str, Any]:
    host, port = parse_server_host_port(server)
    kwargs: dict[str, Any] = {
        "host": host,
        "port": port,
        "username": server.username,
        "known_hosts": known_hosts,
        "connect_timeout": connect_timeout,
        "login_timeout": login_timeout,
    }

    if keepalive_interval is not None:
        kwargs["keepalive_interval"] = keepalive_interval
    if keepalive_count_max is not None:
        kwargs["keepalive_count_max"] = keepalive_count_max

    tunnel = _network_tunnel(getattr(server, "network_config", None))
    if tunnel:
        kwargs["tunnel"] = tunnel

    if server.auth_method == "password":
        if not secret:
            raise ValueError(
                "Не удалось получить пароль сервера. Проверь сохранённый пароль сервера и MASTER_PASSWORD в .env."
            )
        kwargs["password"] = secret
    elif server.auth_method == "key":
        if not (server.key_path or "").strip():
            raise ValueError("Не указан путь к SSH ключу (key auth)")
        kwargs["client_keys"] = [server.key_path]
    elif server.auth_method == "key_password":
        if not (server.key_path or "").strip():
            raise ValueError("Не указан путь к SSH ключу (key+password auth)")
        if not secret:
            raise ValueError(
                "Не удалось получить пасфразу ключа. Проверь сохранённый секрет сервера и MASTER_PASSWORD в .env."
            )
        kwargs["client_keys"] = [server.key_path]
        kwargs["passphrase"] = secret
    else:
        raise ValueError(f"Неизвестный auth_method: {server.auth_method}")

    return kwargs


def _save_server_trusted_host_keys(server_id: int, records: list[dict[str, str]]) -> None:
    server = Server.objects.get(id=server_id)
    server.trusted_host_keys = list(records)
    server.save(update_fields=["trusted_host_keys", "updated_at"])


def clear_server_trusted_host_keys(server: Server) -> None:
    server.trusted_host_keys = []


async def fetch_server_host_key(
    host: str,
    port: int,
    *,
    network_config: Any = None,
    connect_timeout: int = 10,
) -> dict[str, str]:
    kwargs: dict[str, Any] = {
        "host": host,
        "port": port,
    }
    tunnel = _network_tunnel(network_config)
    if tunnel:
        kwargs["tunnel"] = tunnel

    try:
        key = await asyncio.wait_for(asyncssh.get_server_host_key(**kwargs), timeout=max(float(connect_timeout or 10), 1.0))
    except asyncio.TimeoutError as exc:
        raise SSHHostKeyVerificationError(f"Таймаут получения SSH host key ({int(connect_timeout or 10)}s)") from exc
    if key is None:
        raise SSHHostKeyVerificationError("SSH сервер не предоставил host key")
    return _serialize_host_key(key)


async def tofu_known_hosts_for_host(
    host: str,
    port: int,
    *,
    network_config: Any = None,
    connect_timeout: int = 10,
) -> tuple[asyncssh.SSHKnownHosts, dict[str, str]]:
    normalized_host, normalized_port = parse_host_port_value(host, port)
    record = await fetch_server_host_key(
        normalized_host,
        normalized_port,
        network_config=network_config,
        connect_timeout=connect_timeout,
    )
    return build_known_hosts(normalized_host, normalized_port, [record]), record


async def ensure_server_known_hosts(server: Server, *, refresh: bool = False) -> asyncssh.SSHKnownHosts:
    records = get_server_trusted_host_keys(server)
    if records and not refresh:
        normalized = normalize_trusted_host_keys(records)
        if normalized != records:
            await sync_to_async(_save_server_trusted_host_keys, thread_sensitive=True)(server.id, normalized)
            server.trusted_host_keys = normalized
            records = normalized
        return build_known_hosts_for_server(server)

    host, port = parse_server_host_port(server)
    record = await fetch_server_host_key(host, port, network_config=server.network_config or {})
    records = [record]
    await sync_to_async(_save_server_trusted_host_keys, thread_sensitive=True)(server.id, records)
    server.trusted_host_keys = records
    return build_known_hosts(host, port, records)
