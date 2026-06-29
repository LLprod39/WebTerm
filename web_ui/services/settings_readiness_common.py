from __future__ import annotations

from pathlib import Path
from typing import Any

SEVERITY_RANK = {"ready": 0, "warning": 1, "error": 2}

SECRET_PLACEHOLDERS = {
    "change-me",
    "changeme",
    "replace-me",
    "replace-with-secret",
    "replace-with-a-long-random-managed-secret-key-at-least-50-characters",
    "replace-with-a-long-random-secret-key-at-least-50-characters",
}


def readiness_check(
    key: str,
    title: str,
    severity: str,
    message: str,
    *,
    action_path: str = "",
    action_label: str = "",
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "key": key,
        "title": title,
        "status": "ready" if severity == "ready" else severity,
        "severity": severity,
        "message": message,
        "action_path": action_path,
        "action_label": action_label,
        "details": details or {},
    }


def has_value(value: Any) -> bool:
    return bool(str(value or "").strip())


def is_placeholder(value: Any) -> bool:
    normalized = str(value or "").strip().lower()
    return bool(normalized) and normalized in SECRET_PLACEHOLDERS


def safe_resolved_path(raw_path: Path) -> str:
    try:
        return str(raw_path.resolve())
    except Exception:
        return str(raw_path)
