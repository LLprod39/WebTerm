from __future__ import annotations

from collections import defaultdict
from typing import Any

from app.agent_kernel.memory.redaction import sanitize_observation_text


def redact_pipeline_text(
    value: Any,
    *,
    limit: int | None = None,
    preserve_values: list[str] | tuple[str, ...] | None = None,
) -> str:
    text = str(value or "")
    placeholders: dict[str, str] = {}
    for index, raw_value in enumerate(preserve_values or []):
        preserved = str(raw_value or "")
        if not preserved or preserved not in text:
            continue
        placeholder = f"__PIPELINE_REDACTION_PRESERVE_{index}__"
        placeholders[placeholder] = preserved
        text = text.replace(preserved, placeholder)

    redacted = sanitize_observation_text(text).text
    for placeholder, preserved in placeholders.items():
        redacted = redacted.replace(placeholder, preserved)
    if limit is not None:
        return redacted[: max(0, int(limit))]
    return redacted


def redact_pipeline_value(value: Any, *, key: str = "", preserve_keys: set[str] | None = None) -> Any:
    if preserve_keys and key in preserve_keys:
        return value
    if value is None:
        return None
    if isinstance(value, dict):
        return {str(child_key): redact_pipeline_value(item, key=str(child_key), preserve_keys=preserve_keys) for child_key, item in value.items()}
    if isinstance(value, list):
        return [redact_pipeline_value(item, preserve_keys=preserve_keys) for item in value]
    if isinstance(value, tuple):
        return [redact_pipeline_value(item, preserve_keys=preserve_keys) for item in value]
    if isinstance(value, (int, float, bool)):
        return value
    return redact_pipeline_text(value)


def redacted_mapping_context(context: dict[str, Any] | None, *, preserve_keys: set[str] | None = None) -> defaultdict[str, Any]:
    return defaultdict(
        str,
        {
            str(key): redact_pipeline_value(value, key=str(key), preserve_keys=preserve_keys)
            for key, value in dict(context or {}).items()
        },
    )


def redacted_execution_context(ctx: Any, *, preserve_keys: set[str] | None = None) -> defaultdict[str, Any]:
    raw_context = ctx.extra.get("context")
    if not isinstance(raw_context, dict):
        raw_context = {}
    return redacted_mapping_context(raw_context, preserve_keys=preserve_keys)


def redacted_node_outputs_payload(node_outputs: dict[str, dict], *, max_output_chars: int = 1000) -> dict[str, dict[str, Any]]:
    return {
        str(node_id): {
            "status": state.get("status"),
            "output": redact_pipeline_text(state.get("output", ""), limit=max_output_chars),
        }
        for node_id, state in node_outputs.items()
    }


def redacted_all_outputs_text(node_outputs: dict[str, dict], *, max_output_chars: int = 2000) -> str:
    return "\n\n".join(
        f"--- [{node_id}] ---\n{redact_pipeline_text((state.get('output') or '').strip(), limit=max_output_chars)}"
        for node_id, state in node_outputs.items()
        if (state.get("output") or "").strip()
    )
