"""Collector v2 remote script for extended fleet metrics.

One POSIX-sh command string executed over SSH. Emits marker-delimited
sections that servers.monitoring.metrics_parsing understands. Every probe is wrapped
so missing tools degrade to an empty section instead of failing the run.

CPU usage is computed from two /proc/stat samples taken ~1s apart, so the
script needs slightly over one second of wall time on the target host.
"""

from __future__ import annotations

SECTION_PREFIX = "==WT2:"
SECTION_SUFFIX = "=="

# Pseudo-filesystems excluded from df; busybox df has no -x so fall back to plain -P.
_DF_EXCLUDES = "-x tmpfs -x devtmpfs -x overlay -x squashfs -x efivarfs"

_SECTIONS: tuple[tuple[str, str], ...] = (
    ("NPROC", "nproc 2>/dev/null || grep -c ^processor /proc/cpuinfo 2>/dev/null || echo 1"),
    ("UPTIME", "cat /proc/uptime 2>/dev/null || true"),
    ("CPU0", "head -1 /proc/stat 2>/dev/null || true"),
    ("NET0", "cat /proc/net/dev 2>/dev/null || true"),
    ("TCP0", "grep ^Tcp: /proc/net/snmp 2>/dev/null || true"),
    ("SLEEP", "sleep 1"),
    ("CPU1", "head -1 /proc/stat 2>/dev/null || true"),
    ("NET1", "cat /proc/net/dev 2>/dev/null || true"),
    ("TCP1", "grep ^Tcp: /proc/net/snmp 2>/dev/null || true"),
    ("LOAD", "cat /proc/loadavg 2>/dev/null || true"),
    (
        "MEM",
        "grep -E '^(MemTotal|MemFree|MemAvailable|Buffers|Cached|SwapTotal|SwapFree|Dirty|Slab):' /proc/meminfo 2>/dev/null || true",
    ),
    ("DISK", f"df -P {_DF_EXCLUDES} 2>/dev/null || df -P 2>/dev/null || true"),
    ("INODES", f"df -P -i {_DF_EXCLUDES} 2>/dev/null || df -P -i 2>/dev/null || true"),
    ("FDS", "cat /proc/sys/fs/file-nr 2>/dev/null || true"),
    ("PROCS", "ps aux --no-headers 2>/dev/null | wc -l || true"),
    ("ZOMBIES", "ps -eo stat= 2>/dev/null | grep -c '^Z' || true"),
    ("TOPCPU", "ps -eo pid,pcpu,pmem,comm --sort=-pcpu --no-headers 2>/dev/null | head -5 || true"),
    ("TOPMEM", "ps -eo pid,pcpu,pmem,comm --sort=-pmem --no-headers 2>/dev/null | head -5 || true"),
    # command -v guard: missing journalctl must yield an empty section (None),
    # not a fake "0 errors" reading from wc -l on empty input.
    (
        "JERR",
        "command -v journalctl >/dev/null 2>&1 && journalctl -p 3 --since '10 minutes ago' -q --no-pager 2>/dev/null | wc -l || true",
    ),
    (
        "JWARN",
        "command -v journalctl >/dev/null 2>&1 && journalctl -p 4..4 --since '10 minutes ago' -q --no-pager 2>/dev/null | wc -l || true",
    ),
    ("REBOOT", "[ -f /var/run/reboot-required ] && echo 1 || echo 0"),
    ("NTP", "timedatectl show -p NTPSynchronized --value 2>/dev/null || true"),
)


def section_marker(name: str) -> str:
    return f"{SECTION_PREFIX}{name}{SECTION_SUFFIX}"


def build_metrics_script() -> str:
    """Full collector command: BEGIN marker, marked sections, END marker."""
    parts: list[str] = [f"echo '{section_marker('BEGIN')}'"]
    for name, command in _SECTIONS:
        if name == "SLEEP":
            parts.append(command)
            continue
        parts.append(f"echo '{section_marker(name)}'")
        parts.append(f"{{ {command}; }} 2>/dev/null")
    parts.append(f"echo '{section_marker('END')}'")
    return "; ".join(parts)
