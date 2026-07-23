from __future__ import annotations

import re
import shlex
from typing import Any

from servers.linux_ui_commands import (
    APT_COMMON_PACKAGES,
    DISK_COMMAND,
    DOCKER_ACTIONS,
    DOCKER_COMMAND,
    LOG_SOURCES,
    NETWORK_COMMAND,
    RPM_COMMON_PACKAGES,
)
from servers.linux_ui_parsers import (
    _as_bool,
    _build_log_source_command,
    _log_source_available,
    _normalize_service_limit,
    _parse_docker_container_rows,
    _parse_docker_stats_rows,
    _parse_key_value_lines,
    _parse_listening_rows,
    _parse_mount_rows,
    _parse_network_interfaces,
    _parse_package_rows,
    _parse_route_rows,
    _parse_size_path_rows,
    _validate_container_ref,
    _validate_service_name,
)
from servers.linux_ui_runtime import _run_command, _run_command_result, get_linux_ui_capabilities
from servers.models import Server


async def get_linux_ui_logs(
    server: Server,
    *,
    secret: str = "",
    source: str = "journal",
    lines: int = 120,
    service: str = "",
) -> dict[str, Any]:
    normalized_source = str(source or "journal").strip().lower()
    if normalized_source not in LOG_SOURCES:
        raise ValueError("Unsupported log source")

    normalized_lines = _normalize_service_limit(lines, default=120, minimum=20, maximum=240)
    meta_script_lines = [
        "if command -v journalctl >/dev/null 2>&1; then printf 'preset_journal=1\\n'; else printf 'preset_journal=0\\n'; fi",
        "if command -v journalctl >/dev/null 2>&1 || command -v systemctl >/dev/null 2>&1; then printf 'preset_service=1\\n'; else printf 'preset_service=0\\n'; fi",
    ]
    for preset_key, preset in LOG_SOURCES.items():
        if preset["kind"] != "file":
            continue
        preset_paths = preset["path"]
        paths = [preset_paths] if isinstance(preset_paths, str) else list(preset_paths)
        file_checks = " || ".join(f"[ -f {shlex.quote(candidate)} ]" for candidate in paths)
        meta_script_lines.append(
            f"if {file_checks}; then printf 'preset_{preset_key}=1\\n'; else printf 'preset_{preset_key}=0\\n'; fi"
        )

    content_command = _build_log_source_command(normalized_source, normalized_lines, service)
    raw = await _run_command(
        server,
        secret=secret,
        command="\n".join(meta_script_lines) + "\nprintf '__CONTENT__\\n'\n" + content_command + "\n",
    )

    meta_raw, _, content = raw.partition("__CONTENT__\n")
    meta = _parse_key_value_lines(meta_raw)
    content_text = content.strip()
    if not content_text:
        content_text = "No log lines available."

    presets = []
    for preset_key, preset in LOG_SOURCES.items():
        presets.append(
            {
                "key": preset_key,
                "label": preset["label"],
                "description": preset["description"],
                "available": _log_source_available(meta, preset_key, service),
            }
        )

    return {
        "source": normalized_source,
        "service": _validate_service_name(service) if normalized_source == "service" and service else "",
        "lines": normalized_lines,
        "content": content_text,
        "presets": presets,
        "available": _log_source_available(meta, normalized_source, service),
    }


async def get_linux_ui_disk(server: Server, *, secret: str = "") -> dict[str, Any]:
    raw = await _run_command(server, secret=secret, command=DISK_COMMAND)
    _, _, mounts_and_rest = raw.partition("__MOUNTS__\n")
    mounts_raw, _, dirs_and_rest = mounts_and_rest.partition("__DIRS__\n")
    dirs_raw, _, logs_and_rest = dirs_and_rest.partition("__LOGS__\n")
    logs_raw, _, cleanup_raw = logs_and_rest.partition("__CLEANUP__\n")

    mounts = _parse_mount_rows(mounts_raw)
    top_directories = _parse_size_path_rows(dirs_raw)
    large_logs = _parse_size_path_rows(logs_raw)
    cleanup_candidates = [line.strip() for line in str(cleanup_raw or "").splitlines() if line.strip()]

    return {
        "summary": {
            "mounts": len(mounts),
            "critical_mounts": sum(1 for item in mounts if (item.get("percent") or 0) >= 90),
            "top_directory_mb": max((item.get("size_mb") or 0) for item in top_directories)
            if top_directories
            else None,
            "largest_log_mb": max((item.get("size_mb") or 0) for item in large_logs) if large_logs else None,
            "cleanup_candidates": len(cleanup_candidates),
        },
        "mounts": mounts,
        "top_directories": top_directories,
        "large_logs": large_logs,
        "cleanup_candidates": cleanup_candidates,
    }


async def get_linux_ui_packages(server: Server, *, secret: str = "") -> dict[str, Any]:
    capabilities = await get_linux_ui_capabilities(server, secret=secret)
    package_manager = capabilities.get("package_manager") or ""
    if package_manager not in {"apt", "dnf", "yum"}:
        return {
            "package_manager": package_manager,
            "installed": [],
            "updates": [],
            "summary": {
                "installed_common": 0,
                "update_candidates": 0,
            },
        }

    if package_manager == "apt":
        package_names = " ".join(shlex.quote(item) for item in APT_COMMON_PACKAGES)
        command = (
            "printf '__INSTALLED__\\n'\n"
            f"for pkg in {package_names}; do dpkg-query -W -f='${{Package}}\\t${{Version}}\\n' \"$pkg\" 2>/dev/null || true; done\n"
            "printf '__UPDATES__\\n'\n"
            "apt list --upgradable 2>/dev/null | sed '1d' | head -n 15\n"
        )
    else:
        package_names = " ".join(shlex.quote(item) for item in RPM_COMMON_PACKAGES)
        update_command = (
            "dnf -q check-update 2>/dev/null" if package_manager == "dnf" else "yum -q check-update 2>/dev/null"
        )
        command = (
            "printf '__INSTALLED__\\n'\n"
            f"rpm -q --qf '%{{NAME}}\\t%{{VERSION}}-%{{RELEASE}}\\n' {package_names} 2>/dev/null | grep -v 'not installed' || true\n"
            "printf '__UPDATES__\\n'\n"
            f"{update_command} | awk 'NF >= 2 && $1 !~ /^Last/ && $1 !~ /^Obsoleting/ {{print $1\"\\t\"$2}}' | head -n 15\n"
        )

    raw = await _run_command(server, secret=secret, command=command)
    _, _, installed_and_rest = raw.partition("__INSTALLED__\n")
    installed_raw, _, updates_raw = installed_and_rest.partition("__UPDATES__\n")

    installed = _parse_package_rows(installed_raw)
    updates = [line.strip() for line in str(updates_raw or "").splitlines() if line.strip()]

    return {
        "package_manager": package_manager,
        "installed": installed,
        "updates": updates,
        "summary": {
            "installed_common": len(installed),
            "update_candidates": len(updates),
        },
    }


async def get_linux_ui_docker(server: Server, *, secret: str = "") -> dict[str, Any]:
    raw = await _run_command(server, secret=secret, command=DOCKER_COMMAND)
    meta_raw, _, error_and_rest = raw.partition("__ERROR__\n")
    error_raw, _, containers_and_rest = error_and_rest.partition("__CONTAINERS__\n")
    containers_raw, _, stats_raw = containers_and_rest.partition("__STATS__\n")

    meta = _parse_key_value_lines(meta_raw)
    error = error_raw.strip()
    stats_by_name = _parse_docker_stats_rows(stats_raw)
    containers = _parse_docker_container_rows(containers_raw, stats_by_name)

    return {
        "ready": _as_bool(meta.get("docker_ready")),
        "error": error,
        "summary": {
            "total": len(containers),
            "running": sum(1 for item in containers if item.get("state") == "running"),
            "exited": sum(1 for item in containers if item.get("state") == "exited"),
            "restarting": sum(1 for item in containers if item.get("state") == "restarting"),
            "paused": sum(1 for item in containers if item.get("state") == "paused"),
        },
        "containers": containers,
    }


async def get_linux_ui_docker_logs(
    server: Server,
    *,
    secret: str = "",
    container: str,
    lines: int = 80,
) -> dict[str, Any]:
    container_ref = _validate_container_ref(container)
    normalized_lines = _normalize_service_limit(lines, default=80, minimum=20, maximum=200)
    content = await _run_command(
        server,
        secret=secret,
        command=f"docker logs --tail {normalized_lines} {shlex.quote(container_ref)} 2>&1\n",
    )
    return {
        "container": container_ref,
        "lines": normalized_lines,
        "content": content.strip() or "No log lines available.",
    }


async def run_linux_ui_docker_action(
    server: Server,
    *,
    secret: str = "",
    container: str,
    action: str,
) -> dict[str, Any]:
    container_ref = _validate_container_ref(container)
    normalized_action = str(action or "").strip().lower()
    if normalized_action not in DOCKER_ACTIONS:
        raise ValueError("Unsupported docker action")

    result = await _run_command_result(
        server,
        secret=secret,
        command=(
            f"docker {normalized_action} {shlex.quote(container_ref)} 2>&1\n"
            "action_exit=$?\n"
            "printf '\\n__ACTION_EXIT__=%s\\n' \"$action_exit\"\n"
            "printf '__INSPECT__\\n'\n"
            f"docker inspect --format '{{{{.State.Status}}}}\\t{{{{.Config.Image}}}}\\t{{{{.Name}}}}' {shlex.quote(container_ref)} 2>&1 || true\n"
        ),
    )
    output = f"{result.get('stdout') or ''}{result.get('stderr') or ''}"
    action_exit = 1
    inspect_excerpt = ""
    if "__ACTION_EXIT__=" in output:
        before_inspect, _, inspect_part = output.partition("__INSPECT__\n")
        exit_match = re.search(r"__ACTION_EXIT__=(\d+)", before_inspect)
        if exit_match:
            action_exit = int(exit_match.group(1))
        inspect_excerpt = inspect_part.strip()

    return {
        "success": action_exit == 0,
        "container": container_ref,
        "action": normalized_action,
        "dangerous": normalized_action == "stop",
        "output": output.strip(),
        "inspect_excerpt": inspect_excerpt,
    }


async def get_linux_ui_network(server: Server, *, secret: str = "") -> dict[str, Any]:
    raw = await _run_command(server, secret=secret, command=NETWORK_COMMAND)
    meta_raw, _, links_and_rest = raw.partition("__LINKS__\n")
    links_raw, _, addrs_and_rest = links_and_rest.partition("__ADDRS__\n")
    addrs_raw, _, routes_and_rest = addrs_and_rest.partition("__ROUTES__\n")
    routes_raw, _, listen_raw = routes_and_rest.partition("__LISTEN__\n")

    meta = _parse_key_value_lines(meta_raw)
    interfaces = _parse_network_interfaces(links_raw, addrs_raw)
    routes = _parse_route_rows(routes_raw)
    listening = _parse_listening_rows(listen_raw)

    return {
        "tools": {
            "ip": _as_bool(meta.get("has_ip")),
            "ss": _as_bool(meta.get("has_ss")),
        },
        "summary": {
            "interfaces": len(interfaces),
            "addresses": sum(len(item.get("addresses") or []) for item in interfaces),
            "routes": len(routes),
            "listening": len(listening),
        },
        "interfaces": interfaces,
        "routes": routes,
        "listening": listening,
    }
