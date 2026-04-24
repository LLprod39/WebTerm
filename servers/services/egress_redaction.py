"""
B3: Egress redaction for AI responses sent to the user via WebSocket.

Applies :func:`app.agent_kernel.memory.redaction.redact_text` to
text fields in outbound AI events so that secrets inadvertently repeated
by the LLM never reach the client.

Only specific event-type / field combinations are redacted — status
updates and structural events are passed through untouched.

Public API
----------
- ``redact_ai_event(payload) -> tuple[dict, dict]``
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Map of event_type → list of string field names to redact.
_REDACTABLE_FIELDS: dict[str, list[str]] = {
    "ai_response": ["assistant_text"],
    "ai_explanation": ["explanation"],
    "ai_report": ["report"],
    "ai_direct_output": ["output"],
    "ai_recovery": ["why"],
    "ai_question": ["question"],
    "ai_error": ["message"],
}


def redact_ai_event(payload: dict[str, Any]) -> tuple[dict[str, Any], dict[str, int]]:
    """Redact secret-bearing fields in an outbound AI event *in place*.

    Returns ``(payload, report)`` where *report* is a dict of
    ``{pattern_label: count}`` from the redaction engine.  If nothing was
    redacted, *report* is empty.

    The function is intentionally best-effort: import or runtime errors
    fall back to the original payload so the UI is never starved of data.
    """
    event_type = payload.get("type")
    fields = _REDACTABLE_FIELDS.get(event_type)  # type: ignore[arg-type]
    if not fields:
        return payload, {}

    try:
        from app.agent_kernel.memory.redaction import redact_text
    except Exception:  # noqa: BLE001
        return payload, {}

    merged_report: dict[str, int] = {}
    for field in fields:
        raw = payload.get(field)
        if not raw or not isinstance(raw, str):
            continue
        result = redact_text(raw)
        if result.report:
            payload[field] = result.text
            for label, count in result.report.items():
                merged_report[label] = merged_report.get(label, 0) + count

    if merged_report:
        logger.info(
            "B3 egress redaction on %s: %s",
            event_type,
            merged_report,
        )

    return payload, merged_report
