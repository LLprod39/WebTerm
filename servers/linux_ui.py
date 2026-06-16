from __future__ import annotations

import re
import shlex
from typing import Any

from app.tools.safety import is_dangerous_command
from servers.linux_ui_commands import (
    DOCKER_CONTAINER_PATTERN,  # noqa: F401 - compatibility export
    LOG_SOURCES,
    OVERVIEW_COMMAND,
    PROCESS_ACTIONS,
    SERVICE_ACTIONS,
    SERVICE_NAME_PATTERN,  # noqa: F401 - compatibility export
    SETTINGS_COMMAND,
)
from servers.linux_ui_parsers import (
    _as_float,
    _as_int,
    _ensure_systemd_output,
    _kb_to_gb,  # noqa: F401 - compatibility export
    _normalize_service_limit,
    _parse_key_value_lines,
    _parse_marked_sections,
    _parse_process_rows,
    _service_health,
    _validate_pid,
    _validate_service_name,
)
from servers.linux_ui_resources import (
    get_linux_ui_disk,
    get_linux_ui_docker,
    get_linux_ui_docker_logs,
    get_linux_ui_logs,
    get_linux_ui_network,
    get_linux_ui_packages,
    run_linux_ui_docker_action,
)
from servers.linux_ui_runtime import _run_command, _run_command_result, get_linux_ui_capabilities
from servers.models import Server

__all__ = [
    "DOCKER_CONTAINER_PATTERN",
    "LOG_SOURCES",
    "SERVICE_NAME_PATTERN",
    "_kb_to_gb",
    "_run_command",
    "_run_command_result",
    "get_linux_ui_capabilities",
    "get_linux_ui_disk",
    "get_linux_ui_docker",
    "get_linux_ui_docker_logs",
    "get_linux_ui_logs",
    "get_linux_ui_network",
    "get_linux_ui_overview",
    "get_linux_ui_packages",
    "get_linux_ui_processes",
    "get_linux_ui_service_logs",
    "get_linux_ui_services",
    "get_linux_ui_settings",
    "run_linux_ui_docker_action",
    "run_linux_ui_process_action",
    "run_linux_ui_service_action",
]








async def get_linux_ui_settings(server: Server, *, secret: str = "") -> dict[str, Any]:
    raw = await _run_command(server, secret=secret, command=SETTINGS_COMMAND)
    sections = _parse_marked_sections(raw)

    user_accounts = []
    for line in sections.get("USERS_LIST", "").splitlines():
        parts = [part.strip() for part in line.split(":", 3)]
        if len(parts) != 4:
            continue
        user_accounts.append(
            {
                "name": parts[0],
                "uid": parts[1],
                "home": parts[2],
                "shell": parts[3],
            }
        )

    return {
        "general": {
            "hostname": sections.get("GENERAL_HOSTNAME", "") or server.host,
            "timezone": sections.get("GENERAL_TIMEZONE", "") or "unknown",
            "kernel": sections.get("GENERAL_KERNEL", ""),
            "os_release": sections.get("GENERAL_OS_RELEASE", ""),
            "uptime": sections.get("GENERAL_UPTIME", ""),
            "architecture": sections.get("GENERAL_ARCH", ""),
            "cpu": sections.get("GENERAL_CPU", ""),
            "total_memory": sections.get("GENERAL_MEMORY", ""),
        },
        "users": {
            "current_user": sections.get("USERS_CURRENT", "") or server.username,
            "sudo_group": sections.get("USERS_SUDO_GROUP", "") or "N/A",
            "accounts": user_accounts,
            "logged_in": sections.get("USERS_LOGGED_IN", ""),
            "last_logins": sections.get("USERS_LAST_LOGINS", ""),
        },
        "crontab": {
            "user_crontab": sections.get("CRONTAB_USER", ""),
            "system_crontab": sections.get("CRONTAB_SYSTEM", ""),
            "cron_dirs": sections.get("CRONTAB_DIRS", ""),
            "timers": sections.get("CRONTAB_TIMERS", ""),
        },
        "environment": {
            "shell": sections.get("ENVIRONMENT_SHELL", ""),
            "locale": sections.get("ENVIRONMENT_LOCALE", ""),
            "path_directories": [line for line in sections.get("ENVIRONMENT_PATH", "").splitlines() if line.strip()],
            "variables": sections.get("ENVIRONMENT_VARS", ""),
        },
        "security": {
            "ssh_config": sections.get("SECURITY_SSH_CONFIG", ""),
            "firewall": sections.get("SECURITY_FIREWALL", ""),
            "failed_logins": sections.get("SECURITY_FAILED_LOGINS", ""),
            "listening_ports": sections.get("SECURITY_OPEN_PORTS", ""),
        },
    }


async def get_linux_ui_overview(server: Server, *, secret: str = "") -> dict[str, Any]:
    raw = await _run_command(server, secret=secret, command=OVERVIEW_COMMAND)
    parsed = _parse_key_value_lines(raw)

    load_parts = (parsed.get("loadavg") or "").split()
    load_one = _as_float(load_parts[0]) if len(load_parts) > 0 else None
    load_five = _as_float(load_parts[1]) if len(load_parts) > 1 else None
    load_fifteen = _as_float(load_parts[2]) if len(load_parts) > 2 else None

    memory_total_mb = None
    memory_used_mb = None
    memory_percent = None
    mem_parts = (parsed.get("mem_line") or "").split(",")
    if len(mem_parts) >= 2:
        memory_total_mb = _as_int(mem_parts[0])
        memory_used_mb = _as_int(mem_parts[1])
        if memory_total_mb and memory_used_mb is not None and memory_total_mb > 0:
            memory_percent = round((memory_used_mb / memory_total_mb) * 100, 1)

    disk_total_gb = None
    disk_used_gb = None
    disk_percent = None
    disk_parts = (parsed.get("disk_line") or "").split(",")
    if len(disk_parts) >= 3:
        total_kb = _as_int(disk_parts[0])
        used_kb = _as_int(disk_parts[1])
        disk_total_gb = round(total_kb / (1024 * 1024), 1) if total_kb is not None else None
        disk_used_gb = round(used_kb / (1024 * 1024), 1) if used_kb is not None else None
        disk_percent = _as_float(str(disk_parts[2]).rstrip("%"))

    return {
        "hostname": parsed.get("hostname") or server.host,
        "current_user": parsed.get("current_user") or server.username,
        "home_path": parsed.get("home_path") or "",
        "cwd": parsed.get("cwd") or "",
        "os_name": parsed.get("os_name") or "",
        "kernel": parsed.get("kernel") or "",
        "uptime_seconds": _as_int(parsed.get("uptime_seconds")),
        "process_count": _as_int(parsed.get("process_count")),
        "load": {
            "one": load_one,
            "five": load_five,
            "fifteen": load_fifteen,
        },
        "memory": {
            "total_mb": memory_total_mb,
            "used_mb": memory_used_mb,
            "percent": memory_percent,
        },
        "disk": {
            "mount": "/",
            "total_gb": disk_total_gb,
            "used_gb": disk_used_gb,
            "percent": disk_percent,
        },
    }


async def get_linux_ui_services(server: Server, *, secret: str = "", limit: int = 120) -> dict[str, Any]:
    normalized_limit = _normalize_service_limit(limit)
    raw = await _run_command(
        server,
        secret=secret,
        command=(
            "systemctl list-units --type=service --all --plain --no-legend --no-pager 2>/dev/null "
            f"| sed '/^[[:space:]]*$/d' | head -n {normalized_limit}"
        ),
    )
    _ensure_systemd_output(raw)

    services: list[dict[str, Any]] = []
    for line in str(raw or "").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        parts = stripped.split(None, 4)
        if len(parts) < 4:
            continue
        unit = parts[0]
        load = parts[1]
        active = parts[2]
        sub = parts[3]
        description = parts[4] if len(parts) > 4 else ""
        health = _service_health(active, sub)
        services.append(
            {
                "unit": unit,
                "name": unit[:-8] if unit.endswith(".service") else unit,
                "load": load,
                "active": active,
                "sub": sub,
                "description": description,
                "health": health,
                "is_active": health == "active",
                "is_failed": health == "failed",
            }
        )

    order = {"failed": 0, "activating": 1, "active": 2, "inactive": 3, "deactivating": 4, "other": 5}
    services.sort(key=lambda item: (order.get(str(item.get("health")), 99), str(item.get("unit") or "")))

    summary = {
        "total": len(services),
        "active": sum(1 for item in services if item["health"] == "active"),
        "failed": sum(1 for item in services if item["health"] == "failed"),
        "inactive": sum(1 for item in services if item["health"] == "inactive"),
        "other": sum(1 for item in services if item["health"] not in {"active", "failed", "inactive"}),
    }

    return {
        "services": services,
        "summary": summary,
        "limit": normalized_limit,
    }


async def get_linux_ui_service_logs(
    server: Server,
    *,
    secret: str = "",
    service: str,
    lines: int = 80,
) -> dict[str, Any]:
    unit = _validate_service_name(service)
    normalized_lines = _normalize_service_limit(lines, default=80, minimum=20, maximum=200)
    service_arg = shlex.quote(unit)
    result = await _run_command_result(
        server,
        secret=secret,
        command=(
            "if command -v journalctl >/dev/null 2>&1; then "
            f"journalctl -u {service_arg} -n {normalized_lines} --no-pager -o short-iso 2>/dev/null; "
            "else "
            f"systemctl status {service_arg} --no-pager --lines={normalized_lines} 2>&1 || true; "
            "fi"
        ),
    )
    output = str(result.get("stdout") or "") or str(result.get("stderr") or "")
    _ensure_systemd_output(output)

    source = "journalctl" if output.strip() and "Loaded:" not in output[:120] else "systemctl-status"
    if not output.strip():
        output = "No recent service output."

    return {
        "service": unit,
        "lines": normalized_lines,
        "source": source,
        "content": output,
    }


async def run_linux_ui_service_action(
    server: Server,
    *,
    secret: str = "",
    service: str,
    action: str,
) -> dict[str, Any]:
    unit = _validate_service_name(service)
    normalized_action = str(action or "").strip().lower()
    if normalized_action not in SERVICE_ACTIONS:
        raise ValueError("Unsupported service action")

    service_arg = shlex.quote(unit)
    command = (
        f"systemctl {normalized_action} {service_arg} 2>&1\n"
        "action_exit=$?\n"
        "printf '\\n__ACTION_EXIT__=%s\\n' \"$action_exit\"\n"
        "printf '__STATUS__\\n'\n"
        f"systemctl status {service_arg} --no-pager --lines=18 2>&1 || true\n"
    )
    result = await _run_command_result(server, secret=secret, command=command)
    output = f"{result.get('stdout') or ''}{result.get('stderr') or ''}"
    _ensure_systemd_output(output)

    action_exit = 1
    status_excerpt = output
    if "__ACTION_EXIT__=" in output:
        before_status, _, status_part = output.partition("__STATUS__\n")
        exit_match = re.search(r"__ACTION_EXIT__=(\d+)", before_status)
        if exit_match:
            action_exit = int(exit_match.group(1))
        status_excerpt = status_part.strip() or output.strip()

    return {
        "success": action_exit == 0,
        "service": unit,
        "action": normalized_action,
        "dangerous": is_dangerous_command(f"systemctl {normalized_action} {unit}"),
        "output": output.strip(),
        "status_excerpt": status_excerpt,
    }


async def get_linux_ui_processes(server: Server, *, secret: str = "", limit: int = 80) -> dict[str, Any]:
    normalized_limit = _normalize_service_limit(limit, default=80, minimum=20, maximum=160)
    raw = await _run_command(
        server,
        secret=secret,
        command=(
            "printf 'process_count=%s\\n' \"$(ps -e --no-headers 2>/dev/null | wc -l | tr -d ' ')\"\n"
            "printf '__CPU__\\n'\n"
            f"ps -eo pid=,user=,%cpu=,%mem=,etime=,comm=,args= --sort=-%cpu 2>/dev/null | head -n {normalized_limit}\n"
            "printf '__MEM__\\n'\n"
            f"ps -eo pid=,user=,%cpu=,%mem=,etime=,comm=,args= --sort=-%mem 2>/dev/null | head -n {normalized_limit}\n"
        ),
    )
    parsed_meta = _parse_key_value_lines(raw.partition("__CPU__\n")[0])
    _, _, cpu_and_rest = raw.partition("__CPU__\n")
    cpu_section, _, mem_section = cpu_and_rest.partition("__MEM__\n")

    cpu_processes = _parse_process_rows(cpu_section)
    memory_processes = _parse_process_rows(mem_section)

    return {
        "limit": normalized_limit,
        "summary": {
            "total": _as_int(parsed_meta.get("process_count")) or len(cpu_processes),
            "high_cpu": sum(1 for item in cpu_processes if (item.get("cpu_percent") or 0) >= 20),
            "high_memory": sum(1 for item in memory_processes if (item.get("memory_percent") or 0) >= 10),
        },
        "top_cpu": cpu_processes,
        "top_memory": memory_processes,
    }


async def run_linux_ui_process_action(
    server: Server,
    *,
    secret: str = "",
    pid: int | str,
    action: str,
) -> dict[str, Any]:
    process_id = _validate_pid(pid)
    normalized_action = str(action or "").strip().lower()
    if normalized_action not in PROCESS_ACTIONS:
        raise ValueError("Unsupported process action")

    signal_command = "kill" if normalized_action == "terminate" else "kill -9"
    command = (
        f"{signal_command} {process_id} 2>&1\n"
        "action_exit=$?\n"
        "printf '\\n__ACTION_EXIT__=%s\\n' \"$action_exit\"\n"
        "printf '__PROCESS__\\n'\n"
        f"ps -p {process_id} -o pid=,user=,%cpu=,%mem=,etime=,comm=,args= 2>/dev/null || true\n"
    )
    result = await _run_command_result(server, secret=secret, command=command)
    output = f"{result.get('stdout') or ''}{result.get('stderr') or ''}"
    action_exit = 1
    process_excerpt = ""
    if "__ACTION_EXIT__=" in output:
        before_process, _, process_part = output.partition("__PROCESS__\n")
        exit_match = re.search(r"__ACTION_EXIT__=(\d+)", before_process)
        if exit_match:
            action_exit = int(exit_match.group(1))
        process_excerpt = process_part.strip()

    return {
        "success": action_exit == 0,
        "pid": process_id,
        "action": normalized_action,
        "dangerous": normalized_action == "kill_force",
        "output": output.strip(),
        "still_running": bool(process_excerpt),
        "process_excerpt": process_excerpt,
    }
