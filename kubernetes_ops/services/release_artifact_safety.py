from __future__ import annotations

import re
import urllib.parse
from typing import Any

from app.egress_redaction import redact_egress_text

_ARTIFACT_SENSITIVE_KEY_RE = re.compile(
    r"(?i)(password|passwd|secret|token|credential|authorization|cookie|api[_-]?key|apikey|"
    r"access[_-]?key|refresh[_-]?token|session)"
)
_ARTIFACT_SENSITIVE_QUERY_KEYS = {
    "access_key",
    "access-token",
    "access_token",
    "apikey",
    "api-key",
    "api_key",
    "authorization",
    "cookie",
    "credential",
    "password",
    "refresh_token",
    "secret",
    "session",
    "session_id",
    "token",
}
_ARTIFACT_SAFE_PLACEHOLDERS = {
    "",
    "***",
    "[redacted]",
    "<redacted>",
    "redacted",
    "none",
    "null",
}
_ARTIFACT_ISSUE_LIMIT = 12


def build_kubernetes_release_evidence_artifact_safety_report(payload: Any) -> dict[str, Any]:
    issues: list[dict[str, str]] = []
    checked_fields = _scan_release_evidence_artifact(payload, path="$", issues=issues)
    issue_count = len(issues)
    return {
        "success": issue_count == 0,
        "status": "ready" if issue_count == 0 else "unsafe",
        "checked_fields": checked_fields,
        "issue_count": issue_count,
        "issue_limit": _ARTIFACT_ISSUE_LIMIT,
        "truncated": issue_count > _ARTIFACT_ISSUE_LIMIT,
        "issues": issues[:_ARTIFACT_ISSUE_LIMIT],
    }


def _scan_release_evidence_artifact(
    value: Any,
    *,
    path: str,
    issues: list[dict[str, str]],
    key: str = "",
) -> int:
    checked = 1
    if isinstance(value, dict):
        for child_key, child_value in value.items():
            child_key_text = str(child_key)
            checked += _scan_release_evidence_artifact(
                child_value,
                path=f"{path}.{child_key_text}",
                issues=issues,
                key=child_key_text,
            )
        return checked
    if isinstance(value, list):
        for index, child_value in enumerate(value):
            checked += _scan_release_evidence_artifact(
                child_value,
                path=f"{path}[{index}]",
                issues=issues,
                key=key,
            )
        return checked
    if value is None or isinstance(value, (bool, int, float)):
        return checked

    text = str(value)
    if _ARTIFACT_SENSITIVE_KEY_RE.search(key or "") and not _artifact_scalar_is_safe_placeholder(text):
        _append_artifact_issue(issues, path=path, reason=f"sensitive_key:{key}")

    redaction = redact_egress_text(text)
    if redaction.report:
        labels = ",".join(sorted(redaction.report.keys()))
        _append_artifact_issue(issues, path=path, reason=f"secret_pattern:{labels}")

    parsed = urllib.parse.urlsplit(text)
    if parsed.scheme and parsed.netloc:
        if parsed.username or parsed.password:
            _append_artifact_issue(issues, path=path, reason="credentialed_url")
        sensitive_query_keys = sorted(
            key
            for key, _value in urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
            if key.lower() in _ARTIFACT_SENSITIVE_QUERY_KEYS
        )
        if sensitive_query_keys:
            _append_artifact_issue(
                issues,
                path=path,
                reason=f"sensitive_url_query:{','.join(sensitive_query_keys)}",
            )
    return checked


def _append_artifact_issue(issues: list[dict[str, str]], *, path: str, reason: str) -> None:
    issue = {"path": path, "reason": reason}
    if issue not in issues:
        issues.append(issue)


def _artifact_scalar_is_safe_placeholder(value: str) -> bool:
    text = str(value or "").strip()
    lowered = text.lower()
    return (
        lowered in _ARTIFACT_SAFE_PLACEHOLDERS
        or lowered.startswith("[redacted:")
        or lowered.startswith("env:")
        or text.startswith("$")
    )
