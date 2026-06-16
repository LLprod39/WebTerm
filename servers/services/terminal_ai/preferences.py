"""
Pure Terminal-AI preference normalization helpers.

These helpers intentionally know nothing about Channels, SSH, Django models,
or the consumer lifecycle. They sanitize the client-provided ``ai_settings``
payload into the canonical shape used by the terminal assistant.
"""

from __future__ import annotations

from typing import Any

from app.agent_kernel.sudo_policy import normalize_sudo_policy

DEFAULT_AI_SETTINGS: dict[str, Any] = {
    "memory_enabled": True,
    "memory_ttl_requests": 6,
    "auto_report": "auto",
    "confirm_dangerous_commands": True,
    "allowlist_patterns": [],
    "blocklist_patterns": [],
    "dry_run": False,
    "extra_target_server_ids": [],
    "nova_session_context_enabled": True,
    "nova_recent_activity_enabled": True,
    "nova_sudo_policy": "disabled",
}


def default_ai_settings() -> dict[str, Any]:
    return clone_ai_settings(DEFAULT_AI_SETTINGS)


def parse_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def normalize_pattern_list(raw_value: Any) -> list[str]:
    if isinstance(raw_value, str):
        values = raw_value.replace("\r", "\n").split("\n")
    elif isinstance(raw_value, list):
        values = [str(item or "") for item in raw_value]
    else:
        values = []

    seen: set[str] = set()
    normalized: list[str] = []
    for item in values:
        line = str(item or "").strip()
        if not line:
            continue
        key = line.lower()
        if key in seen:
            continue
        seen.add(key)
        normalized.append(line)
    return normalized[:50]


def normalize_int_list(raw_value: Any) -> list[int]:
    values = raw_value if isinstance(raw_value, list) else []
    normalized: list[int] = []
    seen: set[int] = set()
    for item in values:
        try:
            value = int(item)
        except (TypeError, ValueError):
            continue
        if value <= 0 or value in seen:
            continue
        seen.add(value)
        normalized.append(value)
    return normalized[:5]


def normalize_ai_settings(raw_value: Any) -> dict[str, Any]:
    incoming = raw_value if isinstance(raw_value, dict) else {}
    defaults = default_ai_settings()
    auto_report = str(incoming.get("auto_report") or defaults["auto_report"]).strip().lower()
    if auto_report not in {"auto", "on", "off"}:
        auto_report = str(defaults["auto_report"])

    try:
        ttl = int(incoming.get("memory_ttl_requests") or defaults["memory_ttl_requests"])
    except (TypeError, ValueError):
        ttl = int(defaults["memory_ttl_requests"])
    ttl = max(1, min(ttl, 20))

    return {
        "memory_enabled": parse_bool(incoming.get("memory_enabled"), bool(defaults["memory_enabled"])),
        "memory_ttl_requests": ttl,
        "auto_report": auto_report,
        "confirm_dangerous_commands": parse_bool(
            incoming.get("confirm_dangerous_commands"),
            bool(defaults["confirm_dangerous_commands"]),
        ),
        "allowlist_patterns": normalize_pattern_list(incoming.get("allowlist_patterns")),
        "blocklist_patterns": normalize_pattern_list(incoming.get("blocklist_patterns")),
        "dry_run": parse_bool(incoming.get("dry_run"), bool(defaults["dry_run"])),
        "extra_target_server_ids": normalize_int_list(incoming.get("extra_target_server_ids")),
        "nova_session_context_enabled": parse_bool(
            incoming.get("nova_session_context_enabled"),
            bool(defaults["nova_session_context_enabled"]),
        ),
        "nova_recent_activity_enabled": parse_bool(
            incoming.get("nova_recent_activity_enabled"),
            bool(defaults["nova_recent_activity_enabled"]),
        ),
        "nova_sudo_policy": normalize_sudo_policy(incoming.get("nova_sudo_policy")),
    }


def clone_ai_settings(settings: dict[str, Any] | None) -> dict[str, Any]:
    base = settings or {}
    return {
        "memory_enabled": bool(base.get("memory_enabled", True)),
        "memory_ttl_requests": int(base.get("memory_ttl_requests", 6) or 6),
        "auto_report": str(base.get("auto_report") or "auto"),
        "confirm_dangerous_commands": bool(base.get("confirm_dangerous_commands", True)),
        "allowlist_patterns": list(base.get("allowlist_patterns") or []),
        "blocklist_patterns": list(base.get("blocklist_patterns") or []),
        "dry_run": bool(base.get("dry_run", False)),
        "extra_target_server_ids": normalize_int_list(base.get("extra_target_server_ids")),
        "nova_session_context_enabled": bool(base.get("nova_session_context_enabled", True)),
        "nova_recent_activity_enabled": bool(base.get("nova_recent_activity_enabled", True)),
        "nova_sudo_policy": normalize_sudo_policy(base.get("nova_sudo_policy")),
    }


def is_auto_report_enabled(settings: dict[str, Any], execution_mode: str) -> bool:
    mode = str(settings.get("auto_report") or "auto").strip().lower()
    if mode == "on":
        return True
    if mode == "off":
        return False
    return str(execution_mode or "").strip().lower() == "step"


def normalize_ai_chat_mode(value: Any) -> str:
    mode = str(value or "").strip().lower()
    return mode if mode in {"ask", "agent"} else "agent"
