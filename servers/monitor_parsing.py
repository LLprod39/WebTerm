"""Pure parsers for server monitor SSH command output."""

from __future__ import annotations

import contextlib
import re
from typing import Any


def _parse_loadavg(line: str) -> tuple[float, float, float]:
    parts = line.strip().split()
    if len(parts) >= 3:
        return float(parts[0]), float(parts[1]), float(parts[2])
    return 0.0, 0.0, 0.0


def _parse_free(line: str) -> tuple[int, int, float]:
    """Parse 'Mem:  total  used  free ...' -> (total_mb, used_mb, percent)."""
    parts = line.strip().split()
    if len(parts) >= 3:
        total = int(parts[1])
        used = int(parts[2])
        pct = round(used / total * 100, 1) if total > 0 else 0.0
        return total, used, pct
    return 0, 0, 0.0


def _parse_df(line: str) -> tuple[float, float, float]:
    """Parse df output -> (total_gb, used_gb, percent)."""
    parts = line.strip().split()
    if len(parts) >= 5:
        pct_str = parts[4].rstrip("%")
        try:
            pct = float(pct_str)
        except ValueError:
            pct = 0.0
        total = _size_to_gb(parts[1])
        used = _size_to_gb(parts[2])
        return total, used, pct
    return 0.0, 0.0, 0.0


def _size_to_gb(s: str) -> float:
    s = s.strip().upper()
    try:
        if s.endswith("T"):
            return float(s[:-1]) * 1024
        if s.endswith("G"):
            return float(s[:-1])
        if s.endswith("M"):
            return float(s[:-1]) / 1024
        if s.endswith("K"):
            return float(s[:-1]) / (1024 * 1024)
        return float(s) / (1024 * 1024 * 1024)
    except ValueError:
        return 0.0


def _parse_uptime(line: str) -> int:
    parts = line.strip().split()
    if parts:
        try:
            return int(float(parts[0]))
        except ValueError:
            pass
    return 0


def _parse_proc_stat_line(line: str) -> tuple[int, int] | None:
    """Parse a `cpu ...` /proc/stat line -> (total_ticks, idle_ticks)."""
    parts = line.strip().split()
    if not parts or parts[0] != "cpu":
        return None
    try:
        ticks = [int(value) for value in parts[1:]]
    except ValueError:
        return None
    if len(ticks) < 4:
        return None
    # user nice system idle iowait ... — idle time includes iowait.
    idle_ticks = ticks[3] + (ticks[4] if len(ticks) > 4 else 0)
    return sum(ticks), idle_ticks


def cpu_percent_from_stat_ticks(
    prev_total: int,
    prev_idle: int,
    curr_total: int,
    curr_idle: int,
) -> float | None:
    """CPU usage between two /proc/stat samples; None until a positive delta exists."""
    delta_total = curr_total - prev_total
    delta_idle = curr_idle - prev_idle
    if delta_total <= 0:
        return None
    usage = (1 - delta_idle / delta_total) * 100
    return round(max(0.0, min(100.0, usage)), 1)


def _cpu_percent_from_load(load_1m: float, cpu_count: int) -> float:
    """Normalize 1-minute load average by core count (approximation, not true CPU %)."""
    cores = max(1, int(cpu_count or 1))
    return min(round(float(load_1m) * 100.0 / cores, 1), 100.0)


def _parse_quick_output(raw: str) -> dict[str, Any]:
    lines = [line for line in raw.strip().splitlines() if line.strip()]
    result: dict[str, Any] = {}
    stat_samples: dict[str, tuple[int, int]] = {}

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("CPUSTAT1=") or stripped.startswith("CPUSTAT2="):
            key, _, payload = stripped.partition("=")
            parsed = _parse_proc_stat_line(payload)
            if parsed is not None:
                stat_samples[key] = parsed
            continue
        if stripped.startswith("NPROC="):
            with contextlib.suppress(ValueError):
                nproc = int(stripped.split("=", 1)[1].strip())
                if nproc > 0:
                    result["cpu_count"] = nproc
            continue
        if re.match(r"^\d+\.\d+\s+\d+\.\d+\s+\d+\.\d+", stripped):
            l1, l5, l15 = _parse_loadavg(stripped)
            result["load_1m"] = l1
            result["load_5m"] = l5
            result["load_15m"] = l15
        elif stripped.startswith("Mem:"):
            total, used, pct = _parse_free(stripped)
            result["memory_total_mb"] = total
            result["memory_used_mb"] = used
            result["memory_percent"] = pct
        elif "%" in stripped and ("/" in stripped or "G" in stripped.upper() or "M" in stripped.upper()):
            total, used, pct = _parse_df(stripped)
            result["disk_total_gb"] = total
            result["disk_used_gb"] = used
            result["disk_percent"] = pct
        elif re.match(r"^\d+(\.\d+)?\s+\d+(\.\d+)?$", stripped):
            result["uptime_seconds"] = _parse_uptime(stripped)
        elif re.match(r"^\d+$", stripped):
            val = int(stripped)
            if "uptime_seconds" not in result and val > 100:
                result["uptime_seconds"] = val
            else:
                result["process_count"] = val
        elif stripped.startswith("NET_RX_BYTES="):
            with contextlib.suppress(ValueError):
                result["net_rx_bytes"] = int(stripped.split("=", 1)[1].strip())
        elif stripped.startswith("NET_TX_BYTES="):
            with contextlib.suppress(ValueError):
                result["net_tx_bytes"] = int(stripped.split("=", 1)[1].strip())

    # Prefer real CPU utilization from dual /proc/stat samples (same model as live metrics).
    s1 = stat_samples.get("CPUSTAT1")
    s2 = stat_samples.get("CPUSTAT2")
    if s1 and s2:
        cpu = cpu_percent_from_stat_ticks(s1[0], s1[1], s2[0], s2[1])
        if cpu is not None:
            result["cpu_percent"] = cpu
            result["cpu_source"] = "proc_stat"
            return result

    # Fallback: load average normalized by reported core count (never assume 1 core silently
    # when nproc is present — that was the bug that pinned multi-core hosts at 100%).
    if "load_1m" in result:
        cores = int(result.get("cpu_count") or 0)
        if cores <= 0:
            cores = 1
        result["cpu_percent"] = _cpu_percent_from_load(result["load_1m"], cores)
        result["cpu_source"] = "loadavg"
    return result


def _get_cpu_estimate(parsed: dict) -> int:
    """CPU core count from parsed quick output (default 1)."""
    cores = parsed.get("cpu_count")
    if isinstance(cores, int) and cores > 0:
        return cores
    return 1


def _parse_deep_output(raw: str) -> dict[str, Any]:
    result: dict[str, Any] = {"failed_services": [], "log_errors": [], "kernel_errors": []}
    section = "services"
    for line in raw.strip().splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if "UNIT" in stripped and "LOAD" in stripped:
            continue
        if "-- No entries --" in stripped or "-- Journal begins" in stripped:
            continue

        if "failed" in stripped.lower() and ("loaded" in stripped.lower() or ".service" in stripped):
            result["failed_services"].append(stripped.split()[0] if stripped.split() else stripped)
        elif any(k in stripped.lower() for k in ["error", "err", "crit", "alert", "emerg", "fail"]):
            if section == "services":
                section = "logs"
            if section == "logs":
                result["log_errors"].append(stripped[:200])
            else:
                result["kernel_errors"].append(stripped[:200])

    return result


def _parse_docker_output(raw: str) -> dict[str, Any]:
    containers: list[dict[str, str]] = []
    problem_containers: list[dict[str, str]] = []
    for line in raw.strip().splitlines():
        stripped = line.strip()
        if not stripped or "|" not in stripped:
            continue
        name, state, status = (part.strip() for part in stripped.split("|", 2))
        if not name:
            continue
        row = {
            "name": name,
            "state": state.lower(),
            "status": status,
        }
        containers.append(row)
        lowered_status = status.lower()
        if row["state"] != "running" or "unhealthy" in lowered_status:
            problem_containers.append(row)
    return {
        "containers": containers,
        "problem_containers": problem_containers,
    }
