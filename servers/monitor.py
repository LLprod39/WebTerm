"""Compatibility facade for :mod:`servers.monitoring.monitor`."""

from servers.monitoring.monitor import (
    CPU_CRIT,
    CPU_WARN,
    DEEP_COMMANDS,
    DISK_CRIT,
    DISK_WARN,
    DOCKER_MONITOR_COMMAND,
    MEM_CRIT,
    MEM_WARN,
    QUICK_COMMANDS,
    check_all_servers,
    check_server,
    probe_server_lite,
    schedule_health_check_for_server_ids,
)

__all__ = [
    "CPU_CRIT",
    "CPU_WARN",
    "DEEP_COMMANDS",
    "DISK_CRIT",
    "DISK_WARN",
    "DOCKER_MONITOR_COMMAND",
    "MEM_CRIT",
    "MEM_WARN",
    "QUICK_COMMANDS",
    "check_all_servers",
    "check_server",
    "probe_server_lite",
    "schedule_health_check_for_server_ids",
]
