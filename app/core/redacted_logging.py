from __future__ import annotations

from typing import Any

from app.egress_redaction import redact_egress_payload, redact_egress_text


def redacted_log_text(value: object, *, limit: int | None = None) -> str:
    text = redact_egress_text(str(value or "")).text
    if limit is not None and len(text) > limit:
        return text[: max(limit - 3, 0)].rstrip() + "..."
    return text


def redacted_config_value(key: str, value: Any) -> object:
    redacted, _report, _hashes = redact_egress_payload({key: value})
    if isinstance(redacted, dict):
        return redacted.get(key)
    return "[REDACTED]"
