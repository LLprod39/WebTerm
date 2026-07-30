"""Parse live metrics lines from the remote SSH collector loop."""

from __future__ import annotations

import contextlib

REMOTE_LOOP_TEMPLATE = (
    "while :; do "
    "cpu=$(head -n1 /proc/stat); "
    'load=$(cut -d" " -f1-3 /proc/loadavg); '
    "mem=$(awk '/^MemTotal:/{{t=$2}} /^MemAvailable:/{{a=$2}} END{{print t\" \"a}}' /proc/meminfo); "
    'disk=$(df -P / 2>/dev/null | awk \'NR==2{{gsub("%","",$5); print $5}}\'); '
    'echo "LIVE|$cpu|$load|$mem|$disk"; '
    "sleep {interval}; "
    "done"
)


def parse_live_line(line: str) -> dict | None:
    """Parse one `LIVE|<cpu>|<load>|<mem>|<disk>` sample line."""
    parts = line.strip().split("|")
    if len(parts) != 5 or parts[0] != "LIVE":
        return None

    cpu_fields = parts[1].split()
    if not cpu_fields or cpu_fields[0] != "cpu":
        return None
    try:
        ticks = [int(value) for value in cpu_fields[1:]]
    except ValueError:
        return None
    if len(ticks) < 4:
        return None
    # user nice system idle iowait ... — idle time includes iowait.
    idle_ticks = ticks[3] + (ticks[4] if len(ticks) > 4 else 0)

    load_fields = parts[2].split()
    load_1m = None
    if load_fields:
        with contextlib.suppress(ValueError):
            load_1m = float(load_fields[0])

    memory_percent = None
    mem_fields = parts[3].split()
    if len(mem_fields) == 2:
        with contextlib.suppress(ValueError, ZeroDivisionError):
            total_kb = float(mem_fields[0])
            available_kb = float(mem_fields[1])
            if total_kb > 0:
                memory_percent = round((total_kb - available_kb) / total_kb * 100, 1)

    disk_percent = None
    if parts[4].strip():
        with contextlib.suppress(ValueError):
            disk_percent = float(parts[4].strip())

    return {
        "cpu_total_ticks": sum(ticks),
        "cpu_idle_ticks": idle_ticks,
        "load_1m": load_1m,
        "memory_percent": memory_percent,
        "disk_percent": disk_percent,
    }


def compute_cpu_percent(prev: dict, current: dict) -> float | None:
    """CPU usage between two /proc/stat samples; None until two ticks exist."""
    delta_total = current["cpu_total_ticks"] - prev["cpu_total_ticks"]
    delta_idle = current["cpu_idle_ticks"] - prev["cpu_idle_ticks"]
    if delta_total <= 0:
        return None
    usage = (1 - delta_idle / delta_total) * 100
    return round(max(0.0, min(100.0, usage)), 1)
