"""Parsers for collector v2 output (servers.monitoring.metrics_script).

build_metrics_v2() turns raw marker-delimited output into one flat dict that
is a superset of the legacy quick-check metrics: legacy keys (cpu_percent,
memory_percent, disk_percent, ...) stay so ServerHealthCheck and alerting
keep working, extended keys feed ServerMetricSample.

Returns None when the output does not look like collector v2 output so the
caller can fall back to the legacy QUICK_COMMANDS path.
"""

from __future__ import annotations

import re
from typing import Any

from servers.monitoring.metrics_script import SECTION_PREFIX, SECTION_SUFFIX

_MARKER_RE = re.compile(re.escape(SECTION_PREFIX) + r"([A-Z0-9]+)" + re.escape(SECTION_SUFFIX))

_SKIP_FILESYSTEMS = {"tmpfs", "devtmpfs", "overlay", "squashfs", "udev", "none", "efivarfs"}
_SKIP_MOUNT_PREFIXES = ("/dev", "/sys", "/proc", "/run", "/snap", "/mnt/wsl")
_MAX_MOUNTS = 12
_MAX_TOP_PROCESSES = 5
# Nominal interval between the two /proc/stat, /proc/net/dev and Tcp: samples.
SAMPLE_INTERVAL_SECONDS = 1.0


def _to_int(value: Any) -> int | None:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def _to_float(value: Any) -> float | None:
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def split_sections(raw: str) -> dict[str, list[str]] | None:
    """Split collector output into {SECTION: [lines]}; None if markers are absent."""
    sections: dict[str, list[str]] = {}
    current: str | None = None
    for line in (raw or "").splitlines():
        stripped = line.strip()
        match = _MARKER_RE.fullmatch(stripped)
        if match:
            current = match.group(1)
            sections.setdefault(current, [])
            continue
        if current and stripped:
            sections[current].append(stripped)
    if "BEGIN" not in sections or "END" not in sections:
        return None
    return sections


def _first_line(sections: dict[str, list[str]], name: str) -> str:
    lines = sections.get(name) or []
    return lines[0] if lines else ""


# --- CPU ---------------------------------------------------------------


def parse_cpu_ticks(line: str) -> dict[str, int] | None:
    """Parse aggregate '/proc/stat' cpu line into named tick counters."""
    parts = line.split()
    if len(parts) < 5 or parts[0] != "cpu":
        return None
    values = [_to_int(item) or 0 for item in parts[1:]]
    values += [0] * (10 - len(values))
    keys = ["user", "nice", "system", "idle", "iowait", "irq", "softirq", "steal", "guest", "guest_nice"]
    return dict(zip(keys, values, strict=False))


def compute_cpu_usage(line0: str, line1: str) -> dict[str, float]:
    """CPU busy/iowait/steal percentages from two /proc/stat samples."""
    t0 = parse_cpu_ticks(line0)
    t1 = parse_cpu_ticks(line1)
    if not t0 or not t1:
        return {}
    total0 = sum(t0[k] for k in ("user", "nice", "system", "idle", "iowait", "irq", "softirq", "steal"))
    total1 = sum(t1[k] for k in ("user", "nice", "system", "idle", "iowait", "irq", "softirq", "steal"))
    total_delta = total1 - total0
    if total_delta <= 0:
        return {}
    idle_delta = (t1["idle"] - t0["idle"]) + (t1["iowait"] - t0["iowait"])
    busy = max(0.0, (total_delta - idle_delta) / total_delta * 100.0)
    iowait = max(0.0, (t1["iowait"] - t0["iowait"]) / total_delta * 100.0)
    steal = max(0.0, (t1["steal"] - t0["steal"]) / total_delta * 100.0)
    return {
        "cpu_percent": round(min(busy, 100.0), 1),
        "cpu_iowait_percent": round(min(iowait, 100.0), 1),
        "cpu_steal_percent": round(min(steal, 100.0), 1),
    }


# --- Memory ------------------------------------------------------------


def parse_meminfo(lines: list[str]) -> dict[str, Any]:
    kb: dict[str, int] = {}
    for line in lines:
        parts = line.replace(":", " ").split()
        if len(parts) >= 2:
            value = _to_int(parts[1])
            if value is not None:
                kb[parts[0]] = value

    total_kb = kb.get("MemTotal")
    if not total_kb:
        return {}
    available_kb = kb.get("MemAvailable")
    if available_kb is None:
        available_kb = kb.get("MemFree", 0) + kb.get("Buffers", 0) + kb.get("Cached", 0)
    used_kb = max(0, total_kb - available_kb)

    result: dict[str, Any] = {
        "memory_total_mb": total_kb // 1024,
        "memory_available_mb": available_kb // 1024,
        "memory_used_mb": used_kb // 1024,
        "memory_percent": round(used_kb / total_kb * 100, 1),
    }
    swap_total_kb = kb.get("SwapTotal", 0)
    swap_free_kb = kb.get("SwapFree", 0)
    result["swap_total_mb"] = swap_total_kb // 1024
    result["swap_used_mb"] = max(0, swap_total_kb - swap_free_kb) // 1024
    result["swap_percent"] = (
        round((swap_total_kb - swap_free_kb) / swap_total_kb * 100, 1) if swap_total_kb > 0 else 0.0
    )
    return result


# --- Disks -------------------------------------------------------------


def parse_df_mounts(lines: list[str]) -> list[dict[str, Any]]:
    """Parse `df -P` (KB blocks) into per-mount usage entries."""
    mounts: list[dict[str, Any]] = []
    seen: set[str] = set()
    for line in lines:
        parts = line.split()
        if len(parts) < 6 or parts[0] == "Filesystem":
            continue
        filesystem = parts[0]
        mount = " ".join(parts[5:])
        percent_text = parts[4].rstrip("%")
        total_kb = _to_int(parts[1])
        used_kb = _to_int(parts[2])
        percent = _to_float(percent_text)
        if filesystem.lower() in _SKIP_FILESYSTEMS or not mount.startswith("/"):
            continue
        if mount != "/" and mount.startswith(_SKIP_MOUNT_PREFIXES):
            continue
        if mount in seen or total_kb is None or used_kb is None or percent is None:
            continue
        seen.add(mount)
        mounts.append(
            {
                "mount": mount,
                "filesystem": filesystem,
                "total_gb": round(total_kb / 1024 / 1024, 2),
                "used_gb": round(used_kb / 1024 / 1024, 2),
                "percent": percent,
            }
        )
    mounts.sort(key=lambda item: item["total_gb"], reverse=True)
    return mounts[:_MAX_MOUNTS]


def parse_df_inodes(lines: list[str]) -> dict[str, float]:
    """Parse `df -P -i` into {mount: inode_use_percent}."""
    result: dict[str, float] = {}
    for line in lines:
        parts = line.split()
        if len(parts) < 6 or parts[0] == "Filesystem":
            continue
        mount = " ".join(parts[5:])
        percent = _to_float(parts[4].rstrip("%"))
        if mount.startswith("/") and percent is not None:
            result.setdefault(mount, percent)
    return result


# --- Network -----------------------------------------------------------


def parse_net_dev_totals(lines: list[str]) -> dict[str, int] | None:
    """Sum rx/tx bytes and errors+drops across non-loopback interfaces."""
    rx_bytes = tx_bytes = rx_problems = tx_problems = 0
    found = False
    for line in lines:
        if ":" not in line:
            continue
        iface, _, data = line.partition(":")
        iface = iface.strip()
        if not iface or iface == "lo":
            continue
        fields = data.split()
        if len(fields) < 12:
            continue
        values = [_to_int(item) or 0 for item in fields]
        rx_bytes += values[0]
        rx_problems += values[2] + values[3]
        tx_bytes += values[8]
        tx_problems += values[10] + values[11]
        found = True
    if not found:
        return None
    return {
        "rx_bytes": rx_bytes,
        "tx_bytes": tx_bytes,
        "rx_problems": rx_problems,
        "tx_problems": tx_problems,
    }


def compute_net_rates(lines0: list[str], lines1: list[str]) -> dict[str, Any]:
    totals0 = parse_net_dev_totals(lines0)
    totals1 = parse_net_dev_totals(lines1)
    if not totals1:
        return {}
    result: dict[str, Any] = {
        "net_rx_bytes": totals1["rx_bytes"],
        "net_tx_bytes": totals1["tx_bytes"],
    }
    if totals0:
        interval = SAMPLE_INTERVAL_SECONDS
        result["net_rx_bps"] = max(0.0, (totals1["rx_bytes"] - totals0["rx_bytes"]) / interval)
        result["net_tx_bps"] = max(0.0, (totals1["tx_bytes"] - totals0["tx_bytes"]) / interval)
        result["net_errors_per_sec"] = max(
            0.0,
            (totals1["rx_problems"] + totals1["tx_problems"] - totals0["rx_problems"] - totals0["tx_problems"])
            / interval,
        )
    return result


def parse_tcp_snmp(lines: list[str]) -> dict[str, int]:
    """Parse the two `Tcp:` lines of /proc/net/snmp (header + values)."""
    header: list[str] = []
    values: list[int] = []
    for line in lines:
        parts = line.split()
        if len(parts) < 2 or parts[0] != "Tcp:":
            continue
        if _to_int(parts[1]) is None:
            header = parts[1:]
        else:
            values = [_to_int(item) or 0 for item in parts[1:]]
    if not header or len(values) != len(header):
        return {}
    return dict(zip(header, values, strict=True))


def compute_tcp_stats(lines0: list[str], lines1: list[str]) -> dict[str, Any]:
    tcp0 = parse_tcp_snmp(lines0)
    tcp1 = parse_tcp_snmp(lines1)
    if not tcp1:
        return {}
    result: dict[str, Any] = {}
    if "CurrEstab" in tcp1:
        result["tcp_established"] = tcp1["CurrEstab"]
    if tcp0 and "RetransSegs" in tcp0 and "RetransSegs" in tcp1:
        result["tcp_retrans_per_sec"] = max(0.0, (tcp1["RetransSegs"] - tcp0["RetransSegs"]) / SAMPLE_INTERVAL_SECONDS)
    return result


# --- Processes and misc -------------------------------------------------


def parse_top_processes(lines: list[str]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in lines[:_MAX_TOP_PROCESSES]:
        parts = line.split(None, 3)
        if len(parts) < 4:
            continue
        pid = _to_int(parts[0])
        cpu = _to_float(parts[1])
        mem = _to_float(parts[2])
        if pid is None or cpu is None or mem is None:
            continue
        rows.append({"pid": pid, "cpu_percent": cpu, "memory_percent": mem, "command": parts[3][:80]})
    return rows


def parse_file_nr(line: str) -> dict[str, int]:
    parts = line.split()
    if len(parts) < 3:
        return {}
    allocated = _to_int(parts[0])
    unused = _to_int(parts[1])
    maximum = _to_int(parts[2])
    if allocated is None or maximum is None or maximum <= 0:
        return {}
    return {"fd_used": max(0, allocated - (unused or 0)), "fd_max": maximum}


def _parse_bool_line(line: str, true_values: tuple[str, ...]) -> bool | None:
    text = line.strip().lower()
    if not text:
        return None
    return text in true_values


# --- Entry point ---------------------------------------------------------


def build_metrics_v2(raw: str) -> dict[str, Any] | None:
    """Parse collector v2 output into a flat metrics dict (None → fall back)."""
    sections = split_sections(raw)
    if sections is None:
        return None

    metrics: dict[str, Any] = {"collector_version": 2}

    cpu_count = _to_int(_first_line(sections, "NPROC"))
    metrics["cpu_count"] = max(1, cpu_count or 1)

    uptime_parts = _first_line(sections, "UPTIME").split()
    if uptime_parts:
        uptime = _to_float(uptime_parts[0])
        if uptime is not None:
            metrics["uptime_seconds"] = int(uptime)

    load_parts = _first_line(sections, "LOAD").split()
    if len(load_parts) >= 3:
        for key, value in zip(("load_1m", "load_5m", "load_15m"), load_parts[:3], strict=True):
            parsed = _to_float(value)
            if parsed is not None:
                metrics[key] = parsed

    metrics.update(compute_cpu_usage(_first_line(sections, "CPU0"), _first_line(sections, "CPU1")))
    if "cpu_percent" not in metrics and "load_1m" in metrics:
        metrics["cpu_percent"] = round(min(metrics["load_1m"] * 100.0 / metrics["cpu_count"], 100.0), 1)

    metrics.update(parse_meminfo(sections.get("MEM") or []))

    mounts = parse_df_mounts(sections.get("DISK") or [])
    inode_percents = parse_df_inodes(sections.get("INODES") or [])
    for mount in mounts:
        inode_percent = inode_percents.get(mount["mount"])
        if inode_percent is not None:
            mount["inode_percent"] = inode_percent
    if mounts:
        metrics["disk_mounts"] = mounts
        root = next((item for item in mounts if item["mount"] == "/"), mounts[0])
        metrics["disk_percent"] = root["percent"]
        metrics["disk_used_gb"] = root["used_gb"]
        metrics["disk_total_gb"] = root["total_gb"]

    metrics.update(compute_net_rates(sections.get("NET0") or [], sections.get("NET1") or []))
    metrics.update(compute_tcp_stats(sections.get("TCP0") or [], sections.get("TCP1") or []))
    metrics.update(parse_file_nr(_first_line(sections, "FDS")))

    process_count = _to_int(_first_line(sections, "PROCS"))
    if process_count:
        metrics["process_count"] = process_count
    zombie_count = _to_int(_first_line(sections, "ZOMBIES"))
    if zombie_count is not None:
        metrics["zombie_count"] = zombie_count

    top_cpu = parse_top_processes(sections.get("TOPCPU") or [])
    top_mem = parse_top_processes(sections.get("TOPMEM") or [])
    if top_cpu or top_mem:
        metrics["top_processes"] = {"by_cpu": top_cpu, "by_memory": top_mem}

    journal_err = _to_int(_first_line(sections, "JERR"))
    if journal_err is not None:
        metrics["journal_err_10m"] = journal_err
    journal_warn = _to_int(_first_line(sections, "JWARN"))
    if journal_warn is not None:
        metrics["journal_warn_10m"] = journal_warn

    reboot_required = _parse_bool_line(_first_line(sections, "REBOOT"), ("1",))
    if reboot_required is not None:
        metrics["reboot_required"] = reboot_required
    # Older systemd has no `--value`: output is `NTPSynchronized=yes`.
    ntp_line = _first_line(sections, "NTP")
    if "=" in ntp_line:
        ntp_line = ntp_line.rpartition("=")[2]
    ntp_synchronized = _parse_bool_line(ntp_line, ("yes", "1", "true"))
    if ntp_synchronized is not None:
        metrics["ntp_synchronized"] = ntp_synchronized

    if "load_1m" not in metrics and "memory_percent" not in metrics:
        return None
    return metrics
