"""
Loguru sink configuration for production observability.
"""

from __future__ import annotations

import os
import socket
from logging.handlers import SysLogHandler
from pathlib import Path
from threading import Lock
from typing import Any

from django.conf import settings
from loguru import logger

_CONFIGURED = False
_CONFIG_LOCK = Lock()

_LOG_FORMAT = (
    "{time:YYYY-MM-DD HH:mm:ss.SSS} | {level:<8} | "
    "req={extra[request_id]} chan={extra[channel]} user={extra[user_id]} | "
    "{name}:{function}:{line} - {message}"
)


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _record_filter(record: dict[str, Any]) -> bool:
    extra = record.setdefault("extra", {})
    extra.setdefault("request_id", "-")
    extra.setdefault("channel", "-")
    extra.setdefault("user_id", "-")
    return True


def _resolve_log_file_path() -> str:
    raw = (os.getenv("APP_LOG_FILE", "") or "").strip()
    if not raw:
        return ""
    path = Path(raw)
    if not path.is_absolute():
        path = Path(settings.BASE_DIR) / path
    return str(path)


def _resolve_syslog_address() -> str | tuple[str, int]:
    raw = (os.getenv("APP_LOG_SYSLOG_ADDRESS", "") or "").strip()
    if not raw:
        return ("localhost", 514)
    if raw.startswith("/") or raw.startswith("unix://"):
        return raw.removeprefix("unix://")
    host, sep, port = raw.rpartition(":")
    if sep and host and port.isdigit():
        return (host, int(port))
    return (raw, 514)


def _resolve_syslog_facility() -> int:
    raw = (os.getenv("APP_LOG_SYSLOG_FACILITY", "LOG_USER") or "LOG_USER").strip().upper()
    if not raw.startswith("LOG_"):
        raw = f"LOG_{raw}"
    return getattr(SysLogHandler, raw, SysLogHandler.LOG_USER)


def _resolve_syslog_socktype() -> int:
    protocol = (os.getenv("APP_LOG_SYSLOG_PROTOCOL", "udp") or "udp").strip().lower()
    return socket.SOCK_STREAM if protocol == "tcp" else socket.SOCK_DGRAM


def get_log_sink_status() -> dict[str, Any]:
    return {
        "request_id_header": "X-Request-ID",
        "channel_layer_backend": str(
            settings.CHANNEL_LAYERS.get("default", {}).get("BACKEND", "")
        ),
        "log_file_sink_enabled": bool(_resolve_log_file_path()),
        "log_syslog_sink_enabled": _env_bool("APP_LOG_SYSLOG_ENABLED", False),
        "log_level": (os.getenv("APP_LOG_LEVEL", "INFO") or "INFO").strip().upper(),
    }


def configure_loguru_sinks() -> None:
    global _CONFIGURED

    if _CONFIGURED:
        return

    with _CONFIG_LOCK:
        if _CONFIGURED:
            return

        level = (os.getenv("APP_LOG_LEVEL", "INFO") or "INFO").strip().upper()
        enqueue = not bool(getattr(settings, "DEBUG", False))

        file_path = _resolve_log_file_path()
        if file_path:
            try:
                Path(file_path).parent.mkdir(parents=True, exist_ok=True)
                logger.add(
                    file_path,
                    level=level,
                    rotation=(os.getenv("APP_LOG_ROTATION", "50 MB") or "50 MB").strip(),
                    retention=(os.getenv("APP_LOG_RETENTION", "14 days") or "14 days").strip(),
                    enqueue=enqueue,
                    format=_LOG_FORMAT,
                    filter=_record_filter,
                    backtrace=False,
                    diagnose=False,
                )
            except Exception as exc:
                logger.warning("Failed to configure file log sink '{}': {}", file_path, exc)

        if _env_bool("APP_LOG_SYSLOG_ENABLED", False):
            try:
                handler = SysLogHandler(
                    address=_resolve_syslog_address(),
                    facility=_resolve_syslog_facility(),
                    socktype=_resolve_syslog_socktype(),
                )
                logger.add(
                    handler,
                    level=level,
                    enqueue=enqueue,
                    format=_LOG_FORMAT,
                    filter=_record_filter,
                    backtrace=False,
                    diagnose=False,
                )
            except Exception as exc:
                logger.warning("Failed to configure syslog sink: {}", exc)

        _CONFIGURED = True


def log_sink_summary() -> dict[str, Any]:
    data = get_log_sink_status()
    channel_backend = str(data.get("channel_layer_backend") or "")
    return {
        "request_id_header": data["request_id_header"],
        "channel_layer": "redis" if "redis" in channel_backend.lower() else "inmemory",
        "log_file_sink_enabled": bool(data["log_file_sink_enabled"]),
        "log_syslog_sink_enabled": bool(data["log_syslog_sink_enabled"]),
    }
