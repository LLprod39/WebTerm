from __future__ import annotations

import re
import shlex
from typing import Any

from app.tools.safety import is_dangerous_command
from app.tools.ssh_tools import ssh_manager
from servers.models import Server

CAPABILITIES_COMMAND = """
printf 'hostname=%s\n' "$(hostname 2>/dev/null || true)"
printf 'current_user=%s\n' "$(id -un 2>/dev/null || whoami 2>/dev/null || true)"
if [ -r /etc/os-release ]; then
  . /etc/os-release 2>/dev/null
  printf 'os_name=%s\n' "${PRETTY_NAME:-${NAME:-unknown}}"
  printf 'os_id=%s\n' "${ID:-unknown}"
else
  printf 'os_name=\n'
  printf 'os_id=\n'
fi
printf 'kernel=%s\n' "$(uname -srmo 2>/dev/null || true)"
for cmd in systemctl journalctl docker ss ip apt apt-get dnf yum python3 bash sh; do
  if command -v "$cmd" >/dev/null 2>&1; then
    printf 'cmd_%s=1\n' "$cmd"
  else
    printf 'cmd_%s=0\n' "$cmd"
  fi
done
if [ -d /run/systemd/system ] || command -v systemctl >/dev/null 2>&1; then
  printf 'is_systemd=1\n'
else
  printf 'is_systemd=0\n'
fi
"""

OVERVIEW_COMMAND = """
printf 'hostname=%s\n' "$(hostname 2>/dev/null || true)"
printf 'current_user=%s\n' "$(id -un 2>/dev/null || whoami 2>/dev/null || true)"
printf 'home_path=%s\n' "${HOME:-}"
printf 'cwd=%s\n' "$(pwd 2>/dev/null || true)"
if [ -r /etc/os-release ]; then
  . /etc/os-release 2>/dev/null
  printf 'os_name=%s\n' "${PRETTY_NAME:-${NAME:-unknown}}"
else
  printf 'os_name=\n'
fi
printf 'kernel=%s\n' "$(uname -srmo 2>/dev/null || true)"
printf 'uptime_seconds=%s\n' "$(cut -d. -f1 /proc/uptime 2>/dev/null || true)"
printf 'loadavg=%s\n' "$(cut -d' ' -f1-3 /proc/loadavg 2>/dev/null || true)"
printf 'mem_line=%s\n' "$(free -m 2>/dev/null | awk '/^Mem:/ {print $2\",\"$3}')"
printf 'disk_line=%s\n' "$(df -kP / 2>/dev/null | awk 'NR==2 {print $2\",\"$3\",\"$5}')"
printf 'process_count=%s\n' "$(ps aux --no-headers 2>/dev/null | wc -l | tr -d ' ')"
"""

SETTINGS_COMMAND = """
printf '__GENERAL_HOSTNAME__\n'
hostname -f 2>/dev/null || hostname 2>/dev/null || true
printf '\n__GENERAL_TIMEZONE__\n'
timedatectl show --property=Timezone --value 2>/dev/null || cat /etc/timezone 2>/dev/null || echo unknown
printf '\n__GENERAL_KERNEL__\n'
uname -r 2>/dev/null || true
printf '\n__GENERAL_OS_RELEASE__\n'
cat /etc/os-release 2>/dev/null | head -5
printf '\n__GENERAL_UPTIME__\n'
uptime -p 2>/dev/null || uptime 2>/dev/null || true
printf '\n__GENERAL_ARCH__\n'
uname -m 2>/dev/null || true
printf '\n__GENERAL_CPU__\n'
printf '%s\n' "$(nproc 2>/dev/null | tr -d '\n') $(awk -F: '/model name/ {gsub(/^[ \t]+/, "", $2); print $2; exit}' /proc/cpuinfo 2>/dev/null)"
printf '\n__GENERAL_MEMORY__\n'
free -h 2>/dev/null | awk 'NR==2 {print $2}'
printf '\n__USERS_CURRENT__\n'
whoami 2>/dev/null || id -un 2>/dev/null || true
printf '\n__USERS_LIST__\n'
awk -F: '$3 >= 1000 && $3 < 65534 { print $1":"$3":"$6":"$7 }' /etc/passwd 2>/dev/null
printf '\n__USERS_LOGGED_IN__\n'
who 2>/dev/null || w -h 2>/dev/null || true
printf '\n__USERS_LAST_LOGINS__\n'
last -10 2>/dev/null | head -12
printf '\n__USERS_SUDO_GROUP__\n'
getent group sudo 2>/dev/null || getent group wheel 2>/dev/null || echo 'N/A'
printf '\n__CRONTAB_USER__\n'
crontab -l 2>/dev/null || echo 'No crontab for current user'
printf '\n__CRONTAB_SYSTEM__\n'
cat /etc/crontab 2>/dev/null || echo 'No /etc/crontab'
printf '\n__CRONTAB_DIRS__\n'
ls -la /etc/cron.d/ 2>/dev/null | tail -20 || echo 'No /etc/cron.d/'
printf '\n__CRONTAB_TIMERS__\n'
systemctl list-timers --no-pager 2>/dev/null | head -20 || echo 'systemctl unavailable'
printf '\n__ENVIRONMENT_VARS__\n'
env | sort | head -50
printf '\n__ENVIRONMENT_PATH__\n'
echo "${PATH:-}" | tr ':' '\n'
printf '\n__ENVIRONMENT_SHELL__\n'
echo "${SHELL:-}"
printf '\n__ENVIRONMENT_LOCALE__\n'
locale 2>/dev/null | head -5
printf '\n__SECURITY_SSH_CONFIG__\n'
grep -E '^(PermitRootLogin|PasswordAuthentication|PubkeyAuthentication|Port|AllowUsers|AllowGroups)' /etc/ssh/sshd_config 2>/dev/null || echo 'Cannot read sshd_config'
printf '\n__SECURITY_FIREWALL__\n'
ufw status 2>/dev/null || iptables -L -n --line-numbers 2>/dev/null | head -30 || firewall-cmd --list-all 2>/dev/null || echo 'No firewall tool detected'
printf '\n__SECURITY_FAILED_LOGINS__\n'
journalctl -u sshd --no-pager -n 20 --grep='Failed' 2>/dev/null || grep 'Failed' /var/log/auth.log 2>/dev/null | tail -10 || echo 'No failed login data'
printf '\n__SECURITY_OPEN_PORTS__\n'
ss -tlnp 2>/dev/null | head -25 || netstat -tlnp 2>/dev/null | head -25 || echo 'Cannot list ports'
"""

DISK_COMMAND = """
printf '__MOUNTS__\n'
df -kP 2>/dev/null | awk 'NR>1 {print $1"\t"$2"\t"$3"\t"$4"\t"$5"\t"$6}'
printf '__DIRS__\n'
if command -v timeout >/dev/null 2>&1; then
  timeout 12s sh -lc 'du -x -m -d 1 /var /home /srv /opt /tmp /usr/local 2>/dev/null | sort -nr | head -n 18'
else
  du -x -m -d 1 /var /home /srv /opt /tmp /usr/local 2>/dev/null | sort -nr | head -n 18
fi
printf '__LOGS__\n'
if [ -d /var/log ]; then
  if command -v timeout >/dev/null 2>&1; then
    timeout 10s sh -lc 'find /var/log -maxdepth 2 -type f -exec du -m {} + 2>/dev/null | sort -nr | head -n 12'
  else
    find /var/log -maxdepth 2 -type f -exec du -m {} + 2>/dev/null | sort -nr | head -n 12
  fi
fi
printf '__CLEANUP__\n'
if [ -d /tmp ]; then
  find /tmp -mindepth 1 -maxdepth 1 -mtime +7 2>/dev/null | head -n 12
fi
"""

NETWORK_COMMAND = """
if command -v ip >/dev/null 2>&1; then
  printf 'has_ip=1\n'
else
  printf 'has_ip=0\n'
fi
if command -v ss >/dev/null 2>&1; then
  printf 'has_ss=1\n'
else
  printf 'has_ss=0\n'
fi
printf '__LINKS__\n'
if command -v ip >/dev/null 2>&1; then
  ip -o link show 2>/dev/null
fi
printf '__ADDRS__\n'
if command -v ip >/dev/null 2>&1; then
  ip -o addr show 2>/dev/null
fi
printf '__ROUTES__\n'
if command -v ip >/dev/null 2>&1; then
  ip route show 2>/dev/null
elif command -v route >/dev/null 2>&1; then
  route -n 2>/dev/null
fi
printf '__LISTEN__\n'
if command -v ss >/dev/null 2>&1; then
  ss -lntupH 2>/dev/null | head -n 120
elif command -v netstat >/dev/null 2>&1; then
  netstat -lntup 2>/dev/null | tail -n +3 | head -n 120
fi
"""

SERVICE_NAME_PATTERN = re.compile(r"^[A-Za-z0-9_.:@-]+(?:\.service)?$")
DOCKER_CONTAINER_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
SERVICE_ACTIONS = {"start", "stop", "restart", "reload"}
PROCESS_ACTIONS = {"terminate", "kill_force"}
DOCKER_ACTIONS = {"start", "stop", "restart"}
LOG_SOURCES = {
    "journal": {
        "label": "System Journal",
        "description": "Recent lines from journalctl",
        "kind": "journal",
    },
    "service": {
        "label": "Service Journal",
        "description": "Logs for a specific systemd unit",
        "kind": "service",
    },
    "syslog": {
        "label": "syslog",
        "description": "/var/log/syslog",
        "kind": "file",
        "path": "/var/log/syslog",
    },
    "messages": {
        "label": "messages",
        "description": "/var/log/messages",
        "kind": "file",
        "path": "/var/log/messages",
    },
    "auth": {
        "label": "auth.log",
        "description": "/var/log/auth.log",
        "kind": "file",
        "path": "/var/log/auth.log",
    },
    "nginx_error": {
        "label": "nginx error",
        "description": "/var/log/nginx/error.log",
        "kind": "file",
        "path": "/var/log/nginx/error.log",
    },
    "nginx_access": {
        "label": "nginx access",
        "description": "/var/log/nginx/access.log",
        "kind": "file",
        "path": "/var/log/nginx/access.log",
    },
    "apache_error": {
        "label": "apache error",
        "description": "/var/log/apache2/error.log or /var/log/httpd/error_log",
        "kind": "file",
        "path": ["/var/log/apache2/error.log", "/var/log/httpd/error_log"],
    },
    "apache_access": {
        "label": "apache access",
        "description": "/var/log/apache2/access.log or /var/log/httpd/access_log",
        "kind": "file",
        "path": ["/var/log/apache2/access.log", "/var/log/httpd/access_log"],
    },
}
APT_COMMON_PACKAGES = [
    "nginx",
    "docker.io",
    "docker-ce",
    "postgresql",
    "redis-server",
    "python3",
    "nodejs",
    "openssh-server",
]
RPM_COMMON_PACKAGES = [
    "nginx",
    "docker",
    "docker-ce",
    "postgresql-server",
    "redis",
    "python3",
    "nodejs",
    "openssh-server",
]
DOCKER_COMMAND = """
if command -v docker >/dev/null 2>&1; then
  printf 'has_docker=1\n'
  docker info >/dev/null 2>&1
  docker_ready=$?
  if [ "$docker_ready" -eq 0 ]; then
    printf 'docker_ready=1\n'
  else
    printf 'docker_ready=0\n'
  fi
else
  printf 'has_docker=0\n'
  printf 'docker_ready=0\n'
  docker_ready=127
fi
printf '__ERROR__\n'
if [ "${docker_ready:-0}" -ne 0 ] && command -v docker >/dev/null 2>&1; then
  docker info 2>&1 | head -n 20
fi
printf '__CONTAINERS__\n'
if [ "${docker_ready:-0}" -eq 0 ]; then
  docker ps -a --format '{{.ID}}\t{{.Names}}\t{{.Image}}\t{{.State}}\t{{.Status}}\t{{.RunningFor}}\t{{.Ports}}' 2>/dev/null
fi
printf '__STATS__\n'
if [ "${docker_ready:-0}" -eq 0 ]; then
  docker stats --no-stream --format '{{.Name}}\t{{.CPUPerc}}\t{{.MemPerc}}\t{{.MemUsage}}\t{{.NetIO}}\t{{.BlockIO}}' 2>/dev/null
fi
"""


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


async def _run_command(server: Server, *, secret: str = "", command: str) -> str:
    result = await _run_command_result(server, secret=secret, command=command)
    stdout = str(result.get("stdout") or "")
    stderr = str(result.get("stderr") or "")
    return stdout if stdout.strip() else stderr


async def _run_command_result(server: Server, *, secret: str = "", command: str) -> dict[str, Any]:
    conn_id = await ssh_manager.connect(
        host=server.host,
        username=server.username,
        password=secret or None,
        key_path=server.key_path if server.auth_method in ["key", "key_password"] else None,
        port=server.port,
        network_config=server.network_config or {},
        server=server,
    )
    try:
        result = await ssh_manager.execute(conn_id, command)
        return {
            "stdout": str(result.get("stdout") or ""),
            "stderr": str(result.get("stderr") or ""),
            "exit_code": _as_int(str(result.get("exit_code"))) or 0,
        }
    finally:
        await ssh_manager.disconnect(conn_id)


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


async def get_linux_ui_capabilities(server: Server, *, secret: str = "") -> dict[str, Any]:
    raw = await _run_command(server, secret=secret, command=CAPABILITIES_COMMAND)
    parsed = _parse_key_value_lines(raw)

    commands = {
        "systemctl": _as_bool(parsed.get("cmd_systemctl")),
        "journalctl": _as_bool(parsed.get("cmd_journalctl")),
        "docker": _as_bool(parsed.get("cmd_docker")),
        "ss": _as_bool(parsed.get("cmd_ss")),
        "ip": _as_bool(parsed.get("cmd_ip")),
        "apt": _as_bool(parsed.get("cmd_apt")) or _as_bool(parsed.get("cmd_apt-get")),
        "dnf": _as_bool(parsed.get("cmd_dnf")),
        "yum": _as_bool(parsed.get("cmd_yum")),
        "python3": _as_bool(parsed.get("cmd_python3")),
        "bash": _as_bool(parsed.get("cmd_bash")),
        "sh": _as_bool(parsed.get("cmd_sh")),
    }

    package_manager = None
    if commands["apt"]:
        package_manager = "apt"
    elif commands["dnf"]:
        package_manager = "dnf"
    elif commands["yum"]:
        package_manager = "yum"

    return {
        "hostname": parsed.get("hostname") or server.host,
        "current_user": parsed.get("current_user") or server.username,
        "os_name": parsed.get("os_name") or "",
        "os_id": parsed.get("os_id") or "",
        "kernel": parsed.get("kernel") or "",
        "is_systemd": _as_bool(parsed.get("is_systemd")),
        "package_manager": package_manager,
        "commands": commands,
        "available_apps": {
            "overview": True,
            "files": True,
            "terminal": True,
            "ai": True,
            "text_editor": True,
            "quick_run": commands["bash"] or commands["sh"],
            "settings": commands["bash"] or commands["sh"],
            "services": commands["systemctl"],
            "logs": commands["journalctl"],
            "processes": True,
            "disk": True,
            "network": commands["ss"] or commands["ip"],
            "docker": commands["docker"],
            "packages": bool(package_manager),
        },
    }


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
            "top_directory_mb": max((item.get("size_mb") or 0) for item in top_directories) if top_directories else None,
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
            "dnf -q check-update 2>/dev/null"
            if package_manager == "dnf"
            else "yum -q check-update 2>/dev/null"
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
