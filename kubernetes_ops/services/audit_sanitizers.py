from __future__ import annotations

import re
import urllib.parse
from typing import Any

from app.egress_redaction import redact_egress_text

SENSITIVE_KEY_PARTS = ("token", "secret", "password", "credential", "kubeconfig", "authorization", "api_key", "apikey")
SENSITIVE_VALUE_PATTERNS = (
    re.compile(r"(?i)\bbearer\s+[a-z0-9._~+/=-]+"),
    re.compile(r"(?i)(?:token|password|secret|api[_-]?key|kubeconfig|authorization)\s*[:=]\s*[^\"'\s]+"),
    re.compile(r"(?i)(?:client-certificate-data|client-key-data|certificate-authority-data)\s*:"),
)


def safe_audit_payload(value: Any, *, depth: int = 0) -> Any:
    if depth > 6:
        return "[truncated]"
    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}
        for raw_key, raw_value in value.items():
            key = str(raw_key)[:120]
            if _is_sensitive_key(key):
                sanitized[key] = _safe_audit_scalar(raw_value, force_redact=True)
            else:
                sanitized[key] = safe_audit_payload(raw_value, depth=depth + 1)
        return sanitized
    if isinstance(value, list):
        return [safe_audit_payload(item, depth=depth + 1) for item in value[:200]]
    if isinstance(value, tuple):
        return [safe_audit_payload(item, depth=depth + 1) for item in value[:200]]
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return _safe_audit_scalar(value)


def _safe_audit_scalar(value: Any, *, force_redact: bool = False) -> str:
    if force_redact:
        return "[redacted]"
    text = str(value or "")
    parsed = urllib.parse.urlsplit(text.strip())
    if parsed.scheme in {"http", "https"} and parsed.netloc:
        public = _public_link(text)
        return public or "[redacted]"
    if _is_sensitive_value(text):
        return "[redacted]"
    redacted = redact_egress_text(text).text
    if len(redacted) > 1000:
        return f"{redacted[:1000]}...[truncated]"
    return redacted


def _public_link(value: Any) -> str:
    parsed = urllib.parse.urlsplit(str(value or "").strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    host = parsed.hostname or ""
    if not host:
        return ""
    netloc = f"[{host}]" if ":" in host and not host.startswith("[") else host
    try:
        port = parsed.port
    except ValueError:
        port = None
    if port:
        netloc = f"{netloc}:{port}"
    return urllib.parse.urlunsplit((parsed.scheme, netloc, parsed.path or "/", "", ""))[:500]


def _is_sensitive_key(key: str) -> bool:
    normalized = str(key or "").replace("-", "_").lower()
    return any(part in normalized for part in SENSITIVE_KEY_PARTS)


def _is_sensitive_value(value: str) -> bool:
    return any(pattern.search(str(value or "")) for pattern in SENSITIVE_VALUE_PATTERNS)
