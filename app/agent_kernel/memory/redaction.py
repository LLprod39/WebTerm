from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any

_TEXT_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "pem_block",
        re.compile(
            r"-----BEGIN [A-Z0-9 _-]+-----[\s\S]+?-----END [A-Z0-9 _-]+-----",
            re.IGNORECASE,
        ),
    ),
    (
        "bearer_token",
        re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]{12,}\b"),
    ),
    (
        "auth_header",
        re.compile(r"(?im)^(Authorization|X-Api-Key|X-Auth-Token)\s*:\s*.+$"),
    ),
    (
        "connection_string",
        re.compile(
            r"(?i)\b(?:postgres(?:ql)?|mysql|redis|mongodb|amqp|kafka)://[^\s]+"
        ),
    ),
    (
        "secret_assignment",
        re.compile(
            r"(?i)\b(password|passwd|secret|token|api[_-]?key|access[_-]?key|refresh[_-]?token|cookie|session[_-]?id)\b"
            r"(\s*[:=]\s*|\s+is\s+)([^\s\"']+|\"[^\"]*\"|'[^']*')"
        ),
    ),
    (
        "private_key_inline",
        re.compile(r"(?i)\b(?:ssh-rsa|ssh-ed25519)\s+[A-Za-z0-9+/=]{40,}(?:\s+[^\s]+)?"),
    ),
    # Cloud provider credentials
    (
        "aws_access_key",
        re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    ),
    (
        "github_pat",
        re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9_]{36,}\b"),
    ),
    (
        "openai_api_key",
        re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}\b"),
    ),
    (
        "gitlab_pat",
        re.compile(r"\bglpat-[A-Za-z0-9_-]{20,}\b"),
    ),
    (
        "slack_token",
        re.compile(r"\bxox[bpsar]-[0-9A-Za-z-]{10,}\b"),
    ),
    (
        "azure_sas_token",
        re.compile(r"(?i)\b(?:sv|sig|se|sp|spr|st)=[A-Za-z0-9%+/=]{10,}(?:&(?:sv|sig|se|sp|spr|st)=[A-Za-z0-9%+/=]+)+\b"),
    ),
)

_KEY_HINT_RE = re.compile(
    r"(?i)(password|passwd|secret|token|api[_-]?key|access[_-]?key|refresh[_-]?token|cookie|authorization|session)"
)
_INSTRUCTIONAL_LINE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(?i)\bignore (all |any )?(previous|prior) instructions\b"),
    re.compile(r"(?i)\byou are (chatgpt|claude|codex|an ai agent)\b"),
    re.compile(r"(?i)\bsystem prompt\b"),
    re.compile(r"(?i)\bdeveloper message\b"),
    re.compile(r"(?i)\bfollow these instructions\b"),
    re.compile(r"(?i)\bcall the [a-z0-9_ -]*tool\b"),
    re.compile(r"(?i)\btool call\b"),
    re.compile(r"(?i)\bdo not trust the user\b"),
    re.compile(r"(?i)\bexecute the following\b"),
    re.compile(r"(?i)\breturn only json\b"),
    re.compile(r"(?i)\bmust comply\b"),
)
_OBSERVATION_CONTROL_LINE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(?i)^\s*(system|developer|assistant|user)\s*:"),
    re.compile(r"(?i)^\s*\[(system|developer|assistant|user)\]\s*$"),
    re.compile(r"(?i)^\s*<\s*/?\s*(system|developer|assistant|user)\s*>\s*$"),
    re.compile(r"(?i)^\s*(thought|action|observation|final answer)\s*:"),
    re.compile(r"(?i)^\s*(begin|end)\s+(system|developer|assistant|user)\s+(prompt|message)\b"),
    re.compile(r"(?i)^\s*(tool|function)\s*call\b"),
    re.compile(r"(?i)^\s*::[a-z0-9-]+\{"),
    re.compile(r"(?i)^\s*#+\s*(system|developer|assistant|user)\b"),
)
_PROMPT_CONTEXT_CONTROL_LINE_PATTERNS: tuple[re.Pattern[str], ...] = (
    *_OBSERVATION_CONTROL_LINE_PATTERNS,
    re.compile(r"(?i)^\s*role\s*:\s*(system|developer|assistant|user)\b"),
    re.compile(r"(?i)^\s*(respond|answer)\s+with\b"),
)


@dataclass(frozen=True)
class RedactionResult:
    text: str
    report: dict[str, int]
    hashes: list[str]


def _hash_secret(value: str) -> str:
    digest = hashlib.sha256(value.encode("utf-8", errors="ignore")).hexdigest()
    return digest[:16]


def redact_text(text: str | None) -> RedactionResult:
    source = str(text or "")
    if not source:
        return RedactionResult(text="", report={}, hashes=[])

    redacted = source
    report: dict[str, int] = {}
    hashes: list[str] = []

    for label, pattern in _TEXT_PATTERNS:
        def _replace(match: re.Match[str], *, _label: str = label) -> str:
            value = match.group(0)
            report[_label] = report.get(_label, 0) + 1
            hashes.append(_hash_secret(value))
            return f"[REDACTED:{_label}]"

        redacted = pattern.sub(_replace, redacted)

    neutralized_lines: list[str] = []
    for raw_line in redacted.splitlines():
        line = raw_line.strip()
        if line and any(pattern.search(line) for pattern in _INSTRUCTIONAL_LINE_PATTERNS):
            report["instructional_content"] = report.get("instructional_content", 0) + 1
            hashes.append(_hash_secret(line))
            neutralized_lines.append("[FILTERED:instructional_content]")
            continue
        neutralized_lines.append(raw_line)
    redacted = "\n".join(neutralized_lines)

    return RedactionResult(text=redacted, report=report, hashes=hashes)


def sanitize_observation_text(text: str | None) -> RedactionResult:
    base = redact_text(text)
    if not base.text:
        return base

    report = dict(base.report)
    hashes = list(base.hashes)
    sanitized_lines = _sanitize_lines(
        base.text.splitlines(),
        patterns=_OBSERVATION_CONTROL_LINE_PATTERNS,
        report=report,
        hashes=hashes,
        report_key="prompt_injection_content",
        placeholder="[FILTERED:prompt_injection_content]",
    )

    return RedactionResult(
        text="\n".join(sanitized_lines),
        report=report,
        hashes=list(dict.fromkeys(hashes)),
    )


def sanitize_prompt_context_text(text: str | None) -> RedactionResult:
    base = sanitize_observation_text(text)
    if not base.text:
        return base

    report = dict(base.report)
    hashes = list(base.hashes)
    sanitized_lines = _sanitize_lines(
        base.text.splitlines(),
        patterns=_PROMPT_CONTEXT_CONTROL_LINE_PATTERNS,
        report=report,
        hashes=hashes,
        report_key="prompt_context_control_content",
        placeholder="[FILTERED:prompt_context_control_content]",
    )

    return RedactionResult(
        text="\n".join(sanitized_lines),
        report=report,
        hashes=list(dict.fromkeys(hashes)),
    )


def _sanitize_lines(
    lines: list[str],
    *,
    patterns: tuple[re.Pattern[str], ...],
    report: dict[str, int],
    hashes: list[str],
    report_key: str,
    placeholder: str,
) -> list[str]:
    sanitized_lines: list[str] = []
    for raw_line in lines:
        line = raw_line.strip()
        if line and any(pattern.search(line) for pattern in patterns):
            report[report_key] = report.get(report_key, 0) + 1
            hashes.append(_hash_secret(line))
            sanitized_lines.append(placeholder)
            continue
        sanitized_lines.append(raw_line)
    return sanitized_lines


def redact_payload(payload: Any) -> tuple[Any, dict[str, int], list[str]]:
    report: dict[str, int] = {}
    hashes: list[str] = []

    def _merge(child_report: dict[str, int], child_hashes: list[str]) -> None:
        for key, value in child_report.items():
            report[key] = report.get(key, 0) + int(value)
        hashes.extend(child_hashes)

    def _redact(value: Any, *, key_hint: str = "") -> Any:
        if value is None:
            return None
        if isinstance(value, dict):
            return {str(key): _redact(item, key_hint=str(key)) for key, item in value.items()}
        if isinstance(value, list):
            return [_redact(item, key_hint=key_hint) for item in value]
        if isinstance(value, tuple):
            return [_redact(item, key_hint=key_hint) for item in value]
        if isinstance(value, (int, float, bool)):
            return value

        text = str(value)
        if key_hint and _KEY_HINT_RE.search(key_hint):
            secret_hash = _hash_secret(text)
            report["key_hint"] = report.get("key_hint", 0) + 1
            hashes.append(secret_hash)
            return f"[REDACTED:{key_hint.lower()}]"

        child = redact_text(text)
        _merge(child.report, child.hashes)
        return child.text

    redacted_payload = _redact(payload)
    return redacted_payload, report, list(dict.fromkeys(hashes))


def redact_for_storage(*, raw_text: str | None = None, payload: Any | None = None) -> tuple[str, Any, dict[str, int], list[str]]:
    redacted_text = redact_text(raw_text)
    redacted_payload, payload_report, payload_hashes = redact_payload(payload if payload is not None else {})
    report = dict(redacted_text.report)
    for key, value in payload_report.items():
        report[key] = report.get(key, 0) + int(value)
    hashes = list(dict.fromkeys([*redacted_text.hashes, *payload_hashes]))
    return redacted_text.text, redacted_payload, report, hashes


def payload_preview(payload: Any, *, limit: int = 500) -> str:
    if payload in (None, "", {}, []):
        return ""
    try:
        serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    except TypeError:
        serialized = str(payload)
    serialized = serialized.replace("\r", "\n").strip()
    if len(serialized) <= limit:
        return serialized
    return serialized[: max(limit - 3, 0)].rstrip() + "..."
