from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from django.conf import settings


@dataclass(frozen=True)
class RuntimeLimitDefinition:
    field: str
    setting: str
    default: int
    minimum: int = 0
    maximum: int = 86_400


RUNTIME_LIMIT_DEFINITIONS: tuple[RuntimeLimitDefinition, ...] = (
    RuntimeLimitDefinition("agent_active_runs_per_user_limit", "AGENT_ACTIVE_RUNS_PER_USER_LIMIT", 5, maximum=100),
    RuntimeLimitDefinition("agent_active_runs_global_limit", "AGENT_ACTIVE_RUNS_GLOBAL_LIMIT", 25, maximum=500),
    RuntimeLimitDefinition("agent_run_stale_seconds", "AGENT_RUN_STALE_SECONDS", 21_600, maximum=604_800),
    RuntimeLimitDefinition("pipeline_active_runs_per_user_limit", "PIPELINE_ACTIVE_RUNS_PER_USER_LIMIT", 8, maximum=100),
    RuntimeLimitDefinition("pipeline_active_runs_global_limit", "PIPELINE_ACTIVE_RUNS_GLOBAL_LIMIT", 40, maximum=500),
    RuntimeLimitDefinition("pipeline_run_stale_seconds", "PIPELINE_RUN_STALE_SECONDS", 21_600, maximum=604_800),
    RuntimeLimitDefinition("ssh_terminal_sessions_per_user_limit", "SSH_TERMINAL_SESSIONS_PER_USER_LIMIT", 12, maximum=100),
    RuntimeLimitDefinition("ssh_terminal_sessions_global_limit", "SSH_TERMINAL_SESSIONS_GLOBAL_LIMIT", 120, maximum=1_000),
    RuntimeLimitDefinition("ssh_terminal_session_stale_seconds", "SSH_TERMINAL_SESSION_STALE_SECONDS", 180, maximum=86_400),
    RuntimeLimitDefinition("llm_daily_token_limit_per_user", "LLM_DAILY_TOKEN_LIMIT_PER_USER", 0, maximum=50_000_000),
    RuntimeLimitDefinition("mcp_stdio_initialize_timeout_seconds", "MCP_STDIO_INITIALIZE_TIMEOUT_SECONDS", 20, minimum=1, maximum=600),
    RuntimeLimitDefinition("mcp_stdio_request_timeout_seconds", "MCP_STDIO_REQUEST_TIMEOUT_SECONDS", 30, minimum=1, maximum=600),
    RuntimeLimitDefinition("mcp_stdio_tool_call_timeout_seconds", "MCP_STDIO_TOOL_CALL_TIMEOUT_SECONDS", 120, minimum=1, maximum=3_600),
    RuntimeLimitDefinition("mcp_process_terminate_timeout_seconds", "MCP_PROCESS_TERMINATE_TIMEOUT_SECONDS", 2, minimum=1, maximum=60),
    RuntimeLimitDefinition("mcp_http_connect_timeout_seconds", "MCP_HTTP_CONNECT_TIMEOUT_SECONDS", 10, minimum=1, maximum=300),
    RuntimeLimitDefinition("mcp_http_request_timeout_seconds", "MCP_HTTP_REQUEST_TIMEOUT_SECONDS", 30, minimum=1, maximum=600),
    RuntimeLimitDefinition("mcp_http_tool_call_timeout_seconds", "MCP_HTTP_TOOL_CALL_TIMEOUT_SECONDS", 120, minimum=1, maximum=3_600),
    RuntimeLimitDefinition("mcp_http_retry_attempts", "MCP_HTTP_RETRY_ATTEMPTS", 2, maximum=10),
)

_DEFINITIONS_BY_FIELD = {item.field: item for item in RUNTIME_LIMIT_DEFINITIONS}
_DEFINITIONS_BY_SETTING = {item.setting: item for item in RUNTIME_LIMIT_DEFINITIONS}

_CONFIG_CACHE: dict[str, Any] = {"path": None, "mtime": None, "data": {}}


def runtime_limit_fields() -> tuple[str, ...]:
    return tuple(item.field for item in RUNTIME_LIMIT_DEFINITIONS)


def runtime_limit_setting_names() -> tuple[str, ...]:
    return tuple(item.setting for item in RUNTIME_LIMIT_DEFINITIONS)


def normalize_runtime_limit(field: str, value: Any) -> int | None:
    definition = _DEFINITIONS_BY_FIELD.get(field)
    if definition is None:
        raise KeyError(field)
    if value is None or value == "":
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid {field}") from exc
    return max(definition.minimum, min(parsed, definition.maximum))


def _model_config_path() -> Path:
    return Path(os.getenv("MODEL_CONFIG_PATH") or ".model_config.json")


def _read_runtime_limit_overrides() -> dict[str, Any]:
    path = _model_config_path()
    try:
        mtime = path.stat().st_mtime
    except OSError:
        _CONFIG_CACHE.update({"path": str(path), "mtime": None, "data": {}})
        return {}

    cache_path = _CONFIG_CACHE.get("path")
    cache_mtime = _CONFIG_CACHE.get("mtime")
    if cache_path == str(path) and cache_mtime == mtime:
        data = _CONFIG_CACHE.get("data")
        return data if isinstance(data, dict) else {}

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        data = {}
    if not isinstance(data, dict):
        data = {}
    _CONFIG_CACHE.update({"path": str(path), "mtime": mtime, "data": data})
    return data


def _env_limit(definition: RuntimeLimitDefinition) -> int:
    raw = getattr(settings, definition.setting, definition.default)
    try:
        parsed = int(raw or 0)
    except (TypeError, ValueError):
        parsed = definition.default
    return max(definition.minimum, min(parsed, definition.maximum))


def get_runtime_limit(field: str) -> int:
    definition = _DEFINITIONS_BY_FIELD[field]
    overrides = _read_runtime_limit_overrides()
    if field in overrides and overrides[field] is not None:
        return normalize_runtime_limit(field, overrides[field]) or 0
    return _env_limit(definition)


def get_runtime_limit_setting(setting_name: str) -> int:
    definition = _DEFINITIONS_BY_SETTING[setting_name]
    return get_runtime_limit(definition.field)


def runtime_limits_payload() -> dict[str, Any]:
    overrides = _read_runtime_limit_overrides()
    values: dict[str, int] = {}
    sources: dict[str, str] = {}
    bounds: dict[str, dict[str, int]] = {}
    for definition in RUNTIME_LIMIT_DEFINITIONS:
        override = overrides.get(definition.field)
        has_override = override is not None
        values[definition.field] = get_runtime_limit(definition.field)
        sources[definition.field] = "web" if has_override else "env"
        bounds[definition.field] = {
            "min": definition.minimum,
            "max": definition.maximum,
            "default": definition.default,
        }
    return {"values": values, "sources": sources, "bounds": bounds}
