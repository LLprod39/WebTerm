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


def _parse_quick_output(raw: str) -> dict[str, Any]:
    lines = [line for line in raw.strip().splitlines() if line.strip()]
    result: dict[str, Any] = {}

    for line in lines:
        stripped = line.strip()
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

    if "load_1m" in result:
        result["cpu_percent"] = min(round(result["load_1m"] * 100 / max(_get_cpu_estimate(result), 1), 1), 100.0)
    return result


def _get_cpu_estimate(parsed: dict) -> int:
    """Rough CPU count estimate based on load context (default 1)."""
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
