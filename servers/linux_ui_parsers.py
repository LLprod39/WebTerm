from __future__ import annotations

import re
import shlex
from typing import Any

from servers.linux_ui_commands import (
    DOCKER_CONTAINER_PATTERN,
    LOG_SOURCES,
    SERVICE_NAME_PATTERN,
)


def _parse_key_value_lines(raw: str) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for line in str(raw or "").splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        parsed[key.strip()] = value.strip()
    return parsed


def _as_bool(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _as_int(value: str | None) -> int | None:
    try:
        return int(str(value or "").strip())
    except (TypeError, ValueError):
        return None


def _as_float(value: str | None) -> float | None:
    try:
        return float(str(value or "").strip())
    except (TypeError, ValueError):
        return None


def _parse_marked_sections(raw: str) -> dict[str, str]:
    sections: dict[str, list[str]] = {}
    current: str | None = None
    for line in str(raw or "").splitlines():
        marker = re.fullmatch(r"__([A-Z0-9_]+)__", line.strip())
        if marker:
            current = marker.group(1)
            sections.setdefault(current, [])
            continue
        if current is not None:
            sections[current].append(line)
    return {key: "\n".join(lines).strip() for key, lines in sections.items()}


def _normalize_service_limit(limit: int | None, *, default: int = 120, minimum: int = 10, maximum: int = 240) -> int:
    try:
        normalized = int(limit or default)
    except (TypeError, ValueError):
        normalized = default
    return max(minimum, min(normalized, maximum))


def _validate_service_name(service: str) -> str:
    unit = str(service or "").strip()
    if not unit:
        raise ValueError("Service name is required")
    if not SERVICE_NAME_PATTERN.fullmatch(unit):
        raise ValueError("Invalid service name")
    return unit if unit.endswith(".service") else f"{unit}.service"


def _validate_pid(pid: int | str) -> int:
    try:
        normalized = int(str(pid or "").strip())
    except (TypeError, ValueError) as exc:
        raise ValueError("Invalid process id") from exc
    if normalized <= 0:
        raise ValueError("Invalid process id")
    return normalized


def _validate_container_ref(value: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise ValueError("Container reference is required")
    if not DOCKER_CONTAINER_PATTERN.fullmatch(normalized):
        raise ValueError("Invalid container reference")
    return normalized


def _parse_process_rows(raw: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in str(raw or "").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        parts = stripped.split(None, 6)
        if len(parts) < 6:
            continue
        pid = _as_int(parts[0])
        cpu_percent = _as_float(parts[2])
        memory_percent = _as_float(parts[3])
        if pid is None:
            continue
        command = parts[5]
        args = parts[6] if len(parts) > 6 else command
        rows.append(
            {
                "pid": pid,
                "user": parts[1],
                "cpu_percent": cpu_percent,
                "memory_percent": memory_percent,
                "elapsed": parts[4],
                "command": command,
                "args": args,
            }
        )
    return rows


def _kb_to_gb(value: int | None) -> float | None:
    if value is None:
        return None
    return round(value / (1024 * 1024), 1)


def _parse_mount_rows(raw: str) -> list[dict[str, Any]]:
    mounts: list[dict[str, Any]] = []
    for line in str(raw or "").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        parts = stripped.split("\t")
        if len(parts) < 6:
            parts = stripped.split(None, 5)
        if len(parts) < 6:
            continue
        total_kb = _as_int(parts[1])
        used_kb = _as_int(parts[2])
        available_kb = _as_int(parts[3])
        percent = _as_float(parts[4].rstrip("%"))
        mounts.append(
            {
                "filesystem": parts[0],
                "mount": parts[5],
                "size_gb": _kb_to_gb(total_kb),
                "used_gb": _kb_to_gb(used_kb),
                "available_gb": _kb_to_gb(available_kb),
                "percent": percent,
            }
        )
    return sorted(mounts, key=lambda item: (-(item.get("percent") or 0), item.get("mount") or ""))


def _parse_size_path_rows(raw: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in str(raw or "").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        parts = stripped.split(None, 1)
        if len(parts) < 2:
            continue
        size_mb = _as_int(parts[0])
        path = parts[1].strip()
        if size_mb is None or not path:
            continue
        rows.append(
            {
                "path": path,
                "size_mb": size_mb,
            }
        )
    return rows


def _parse_package_rows(raw: str) -> list[dict[str, str]]:
    packages: list[dict[str, str]] = []
    for line in str(raw or "").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        parts = stripped.split("\t", 1)
        if len(parts) < 2:
            parts = stripped.split(None, 1)
        if len(parts) < 2:
            continue
        packages.append(
            {
                "name": parts[0].strip(),
                "version": parts[1].strip(),
            }
        )
    return packages


def _parse_docker_stats_rows(raw: str) -> dict[str, dict[str, str]]:
    stats: dict[str, dict[str, str]] = {}
    for line in str(raw or "").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        parts = stripped.split("\t")
        if len(parts) < 6:
            continue
        stats[parts[0]] = {
            "cpu_percent": parts[1],
            "memory_percent": parts[2],
            "memory_usage": parts[3],
            "network_io": parts[4],
            "block_io": parts[5],
        }
    return stats


def _parse_docker_container_rows(raw: str, stats_by_name: dict[str, dict[str, str]]) -> list[dict[str, Any]]:
    containers: list[dict[str, Any]] = []
    for line in str(raw or "").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        parts = stripped.split("\t")
        if len(parts) < 7:
            continue
        container_id, name, image, state, status, running_for, ports = parts[:7]
        state_lower = state.strip().lower()
        stats = stats_by_name.get(name) or {}
        containers.append(
            {
                "id": container_id,
                "name": name,
                "image": image,
                "state": state_lower,
                "status": status,
                "running_for": running_for,
                "ports": ports,
                "cpu_percent": stats.get("cpu_percent", ""),
                "memory_percent": stats.get("memory_percent", ""),
                "memory_usage": stats.get("memory_usage", ""),
                "network_io": stats.get("network_io", ""),
                "block_io": stats.get("block_io", ""),
            }
        )
    return containers


def _parse_network_interfaces(link_raw: str, addr_raw: str) -> list[dict[str, Any]]:
    interfaces: dict[str, dict[str, Any]] = {}
    for line in str(link_raw or "").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        match = re.match(
            r"^\d+:\s+([^:]+):\s+<([^>]*)>.*?\bmtu\s+(\d+)(?:.*?\bstate\s+(\S+))?.*?\blink/(\S+)\s+(\S+)",
            stripped,
        )
        if not match:
            continue
        raw_name, flags_raw, mtu_raw, state_raw, kind_raw, mac_raw = match.groups()
        name = raw_name.split("@", 1)[0]
        flags = [flag for flag in flags_raw.split(",") if flag]
        interfaces[name] = {
            "name": name,
            "state": str(state_raw or ("UP" if "UP" in flags else "DOWN")).upper(),
            "mtu": _as_int(mtu_raw),
            "kind": kind_raw,
            "mac": mac_raw,
            "flags": flags,
            "addresses": [],
        }

    for line in str(addr_raw or "").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        parts = stripped.split()
        if len(parts) < 4:
            continue
        family = parts[2]
        if family not in {"inet", "inet6"}:
            continue
        name = parts[1].split("@", 1)[0]
        scope = ""
        if "scope" in parts:
            scope_index = parts.index("scope")
            if scope_index + 1 < len(parts):
                scope = parts[scope_index + 1]

        entry = interfaces.setdefault(
            name,
            {
                "name": name,
                "state": "UNKNOWN",
                "mtu": None,
                "kind": "unknown",
                "mac": "",
                "flags": [],
                "addresses": [],
            },
        )
        entry["addresses"].append(
            {
                "family": family,
                "address": parts[3],
                "scope": scope,
            }
        )

    return sorted(interfaces.values(), key=lambda item: (item["name"] != "lo", item["name"]))


def _parse_route_rows(raw: str) -> list[str]:
    routes: list[str] = []
    for line in str(raw or "").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.lower().startswith("kernel ip routing table"):
            continue
        if stripped.lower().startswith("destination"):
            continue
        routes.append(stripped)
    return routes


def _parse_listening_rows(raw: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    state_words = {"LISTEN", "UNCONN", "ESTAB", "UNKNOWN"}
    for line in str(raw or "").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        parts = stripped.split(None, 6)
        if len(parts) < 5:
            continue

        protocol = parts[0]
        state = ""
        local_address = ""
        peer_address = ""
        process = ""

        if len(parts) >= 6 and parts[1].upper() in state_words:
            state = parts[1]
            local_address = parts[4] if len(parts) > 4 else ""
            peer_address = parts[5] if len(parts) > 5 else ""
            process = parts[6] if len(parts) > 6 else ""
        else:
            state = parts[5] if len(parts) > 5 else ""
            local_address = parts[3] if len(parts) > 3 else ""
            peer_address = parts[4] if len(parts) > 4 else ""
            process = parts[6] if len(parts) > 6 else ""

        rows.append(
            {
                "protocol": protocol,
                "state": state,
                "local_address": local_address,
                "peer_address": peer_address,
                "process": process,
            }
        )
    return rows


def _build_log_source_command(source: str, lines: int, service: str) -> str:
    preset = LOG_SOURCES[source]
    kind = preset["kind"]
    if kind == "journal":
        return (
            "if command -v journalctl >/dev/null 2>&1; then "
            f"journalctl -n {lines} --no-pager -o short-iso 2>&1; "
            "else "
            "printf 'journalctl is unavailable on this host.\\n'; "
            "fi"
        )
    if kind == "service":
        unit = _validate_service_name(service)
        service_arg = shlex.quote(unit)
        return (
            "if command -v journalctl >/dev/null 2>&1; then "
            f"journalctl -u {service_arg} -n {lines} --no-pager -o short-iso 2>&1; "
            "else "
            f"systemctl status {service_arg} --no-pager --lines={lines} 2>&1 || true; "
            "fi"
        )

    paths = preset["path"]
    path_candidates = [paths] if isinstance(paths, str) else list(paths)

    file_checks = " ".join(f"{shlex.quote(candidate)}" for candidate in path_candidates)
    return (
        f"for candidate in {file_checks}; do "
        "if [ -f \"$candidate\" ]; then "
        f"tail -n {lines} \"$candidate\" 2>&1; "
        "exit 0; "
        "fi; "
        "done; "
        "printf 'Selected log file is unavailable on this host.\\n'"
    )


def _log_source_available(meta: dict[str, str], source: str, service: str) -> bool:
    if source == "service":
        if not service:
            return False
        return _as_bool(meta.get("preset_service"))
    return _as_bool(meta.get(f"preset_{source}"))


def _ensure_systemd_output(raw: str) -> None:
    normalized = str(raw or "").lower()
    if "system has not been booted with systemd" in normalized:
        raise ValueError("systemd is unavailable on this host")
    if "failed to connect to bus" in normalized:
        raise ValueError("Unable to reach the systemd bus on this host")


def _service_health(active: str, sub: str) -> str:
    active_value = str(active or "").strip().lower()
    sub_value = str(sub or "").strip().lower()
    if active_value == "failed" or sub_value == "failed":
        return "failed"
    if active_value == "active":
        return "active"
    if active_value == "activating":
        return "activating"
    if active_value in {"inactive", "maintenance"} or sub_value == "dead":
        return "inactive"
    if active_value == "deactivating":
        return "deactivating"
    return "other"
