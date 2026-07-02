from __future__ import annotations

import re
import urllib.parse
from typing import Any

from kubernetes_ops.services.logs import _redact_log_line

MAX_TEXT = 500
SENSITIVE_KEY_RE = re.compile(
    r"(token|access[_-]?token|refresh[_-]?token|secret|password|credential|authorization|cookie|apikey|api_key)",
    re.I,
)


def sanitize_action_value(value: Any) -> Any:
    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}
        for key, item in value.items():
            safe_key = str(key)[:80]
            sanitized[safe_key] = "[redacted]" if SENSITIVE_KEY_RE.search(safe_key) else sanitize_action_value(item)
        return sanitized
    if isinstance(value, list):
        return [sanitize_action_value(item) for item in value[:25]]
    if isinstance(value, tuple):
        return [sanitize_action_value(item) for item in value[:25]]
    if isinstance(value, str):
        return bounded_action_text(value)
    if value is None or isinstance(value, bool | int | float):
        return value
    return bounded_action_text(str(value))


def sanitize_public_links(value: Any) -> Any:
    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}
        for key, item in value.items():
            safe_key = str(key)[:80]
            sanitized[safe_key] = "[redacted]" if SENSITIVE_KEY_RE.search(safe_key) else sanitize_public_links(item)
        return sanitized
    if isinstance(value, list):
        return [sanitize_public_links(item) for item in value[:25]]
    if isinstance(value, tuple):
        return [sanitize_public_links(item) for item in value[:25]]
    if isinstance(value, str):
        return public_url_or_text(value)
    if value is None or isinstance(value, bool | int | float):
        return value
    return bounded_action_text(str(value))


def public_url_or_text(value: str) -> str:
    text = bounded_action_text(value)
    parsed = urllib.parse.urlsplit(text)
    if not parsed.scheme or not parsed.netloc:
        return text
    host = parsed.hostname or ""
    if not host:
        return ""
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    try:
        port = parsed.port
    except ValueError:
        port = None
    netloc = f"{host}:{port}" if port else host
    return urllib.parse.urlunsplit((parsed.scheme, netloc, parsed.path or "", "", ""))[:MAX_TEXT]


def bounded_action_text(value: Any, *, limit: int = MAX_TEXT) -> str:
    return _redact_log_line(str(value or "").strip())[:limit]


def reference_action_text(value: Any, *, limit: int = MAX_TEXT) -> str:
    text = _redact_log_line(str(value or "").strip())
    parsed = urllib.parse.urlsplit(text)
    if parsed.scheme in {"http", "https"} and parsed.netloc and not any(char.isspace() for char in text):
        host = parsed.hostname or ""
        if host:
            netloc = f"[{host}]" if ":" in host and not host.startswith("[") else host
            try:
                port = parsed.port
            except ValueError:
                port = None
            if port:
                netloc = f"{netloc}:{port}"
            text = urllib.parse.urlunsplit((parsed.scheme, netloc, parsed.path or "", "", ""))
    return text[:limit]
