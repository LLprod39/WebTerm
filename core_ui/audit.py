"""
Audit configuration, context and retention helpers.
"""

from __future__ import annotations

import contextlib
import time
from collections.abc import Iterator
from contextvars import ContextVar
from datetime import timedelta
from threading import Lock
from typing import Any

from django.utils import timezone
from loguru import logger

from app.core.model_config import model_manager

DEFAULT_LOGGING_CONFIG: dict[str, Any] = {
    "log_terminal_commands": True,
    "log_ai_assistant": True,
    "log_agent_runs": True,
    "log_pipeline_runs": True,
    "log_auth_events": True,
    "log_server_changes": True,
    "log_settings_changes": True,
    "log_file_operations": False,
    "log_mcp_calls": True,
    "log_http_requests": True,
    "retention_days": 90,
    "export_format": "json",
}

_CONFIG_LOADED = False
_CONFIG_LOCK = Lock()
_AUDIT_CONTEXT: ContextVar[dict[str, Any]] = ContextVar("weu_audit_context", default={})
_RETENTION_LOCK = Lock()
_LAST_RETENTION_RUN_TS = 0.0
_RETENTION_INTERVAL_SECONDS = 3600.0


def _ensure_config_loaded() -> None:
    global _CONFIG_LOADED
    if _CONFIG_LOADED:
        return
    with _CONFIG_LOCK:
        if _CONFIG_LOADED:
            return
        with contextlib.suppress(Exception):
            model_manager.load_config()
        _CONFIG_LOADED = True


def _coerce_bool(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _coerce_int(value: Any, default: int, *, min_value: int, max_value: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(min_value, min(parsed, max_value))


def get_logging_config() -> dict[str, Any]:
    _ensure_config_loaded()
    config = dict(DEFAULT_LOGGING_CONFIG)
    current = getattr(model_manager, "config", None)
    if current is None:
        return config

    for key, default in DEFAULT_LOGGING_CONFIG.items():
        raw_value = getattr(current, key, default)
        if isinstance(default, bool):
            config[key] = _coerce_bool(raw_value, default)
        elif isinstance(default, int):
            config[key] = _coerce_int(raw_value, default, min_value=1, max_value=3650)
        else:
            text = str(raw_value or default).strip().lower()
            config[key] = text or default

    if config["export_format"] not in {"json", "csv", "syslog"}:
        config["export_format"] = "json"
    return config


def get_audit_context() -> dict[str, Any]:
    return dict(_AUDIT_CONTEXT.get({}) or {})


@contextlib.contextmanager
def audit_context(**values: Any) -> Iterator[None]:
    current = get_audit_context()
    for key, value in values.items():
        if value is None:
            current.pop(key, None)
        else:
            current[key] = value
    token = _AUDIT_CONTEXT.set(current)
    try:
        yield
    finally:
        _AUDIT_CONTEXT.reset(token)


def infer_request_category(path: str) -> str:
    normalized = str(path or "").strip().lower()
    if normalized.startswith("/api/auth/") or normalized in {"/login/", "/logout/"}:
        return "auth"
    if normalized.startswith("/api/settings/") or normalized.startswith("/api/access/") or normalized.startswith("/settings/"):
        return "settings"
    if normalized.startswith("/api/studio/mcp/"):
        return "mcp"
    if normalized.startswith("/api/studio/skills/"):
        return "file"
    if normalized.startswith("/api/studio/agents/"):
        return "agent"
    if normalized.startswith("/api/studio/notifications/"):
        return "settings"
    if normalized.startswith("/api/studio/"):
        return "pipeline"
    if normalized.startswith("/servers/"):
        return "server"
    if normalized.startswith("/api/admin/") or normalized.startswith("/dashboard/"):
        return "agent"
    return "other"


def get_logging_flags_for_event(
    category: str,
    action: str,
    metadata: dict[str, Any] | None = None,
) -> list[str]:
    metadata = metadata or {}
    category_lower = str(category or "").strip().lower()
    action_lower = str(action or "").strip().lower()

    if action_lower == "http_request":
        return ["log_http_requests"]

    if action_lower in {
        "terminal_command",
        "server_execute_command",
        "server_tool_execute",
        "server_command_execute",
        "terminal_ai_command",
    }:
        return ["log_terminal_commands"]

    if action_lower in {
        "chat_request",
        "terminal_ai_request",
        "pipeline_assistant_request",
        "agent_ai_refine",
        "llm_request",
    } or category_lower in {"ai", "assistant"}:
        return ["log_ai_assistant"]

    if category_lower == "agent" or action_lower.startswith("agent_"):
        return ["log_agent_runs"]

    if category_lower == "pipeline" or action_lower.startswith("pipeline_"):
        return ["log_pipeline_runs"]

    if category_lower == "mcp" or action_lower.startswith("mcp_"):
        return ["log_mcp_calls"]

    if category_lower == "file" or action_lower.startswith("file_") or metadata.get("file_operation"):
        return ["log_file_operations"]

    if category_lower == "auth" or action_lower in {"login", "logout", "login_failed", "logout_failed"}:
        return ["log_auth_events"]

    if category_lower == "settings" or action_lower.startswith("settings_") or action_lower.startswith("access_"):
        return ["log_settings_changes"]

    if category_lower in {"server", "servers", "monitoring", "terminal"}:
        return ["log_server_changes"]

    if action_lower.startswith(("server_", "servers_", "monitoring_", "terminal_", "rdp_")):
        return ["log_server_changes"]

    return []


def should_log_activity(
    *,
    category: str,
    action: str,
    metadata: dict[str, Any] | None = None,
) -> bool:
    config = get_logging_config()
    flags = get_logging_flags_for_event(category=category, action=action, metadata=metadata)
    if not flags:
        return True
    return any(bool(config.get(flag, False)) for flag in flags)


def should_log_llm() -> bool:
    return bool(get_logging_config().get("log_ai_assistant", True))


def maybe_apply_log_retention(force: bool = False) -> None:
    global _LAST_RETENTION_RUN_TS

    config = get_logging_config()
    retention_days = _coerce_int(config.get("retention_days"), 90, min_value=1, max_value=3650)
    now_ts = time.monotonic()
    if not force and (now_ts - _LAST_RETENTION_RUN_TS) < _RETENTION_INTERVAL_SECONDS:
        return

    with _RETENTION_LOCK:
        if not force and (now_ts - _LAST_RETENTION_RUN_TS) < _RETENTION_INTERVAL_SECONDS:
            return
        cutoff = timezone.now() - timedelta(days=retention_days)
        try:
            from core_ui.models import LLMUsageLog, UserActivityLog

            UserActivityLog.objects.filter(created_at__lt=cutoff).delete()
            LLMUsageLog.objects.filter(created_at__lt=cutoff).delete()
            _LAST_RETENTION_RUN_TS = now_ts
        except Exception as exc:
            logger.debug("audit retention cleanup failed: {}", exc)
