from __future__ import annotations

from typing import Any

from django.conf import settings

from kubernetes_ops.models import K8sAdminRecording, K8sAdminRecordingEvent
from kubernetes_ops.serializers import serialize_admin_recording, serialize_admin_recording_event
from kubernetes_ops.services.admin_recording import DEFAULT_TRANSCRIPT_EVENT_MAX_CHARS
from kubernetes_ops.services.describe import sanitize_metadata
from kubernetes_ops.services.logs import _redact_log_line


def safe_recording_payload(recording: K8sAdminRecording, *, include_events: bool = False, event_limit: int | str | None = None) -> dict[str, Any]:
    payload = serialize_admin_recording(recording)
    payload["policy_snapshot"] = sanitize_metadata(payload.get("policy_snapshot") or {})
    payload["summary"] = sanitize_metadata(payload.get("summary") or {})
    if include_events:
        payload["events"] = safe_recording_events(recording, limit=event_limit)
    return payload


def safe_recording_events(recording: K8sAdminRecording, *, limit: int | str | None = None) -> list[dict[str, Any]]:
    events = recording.events.order_by("sequence", "id")[:_bounded_limit(limit)]
    return [safe_recording_event_payload(event) for event in events]


def safe_recording_event_payload(event: K8sAdminRecordingEvent) -> dict[str, Any]:
    payload = serialize_admin_recording_event(event)
    payload["data"] = _safe_event_data(payload.get("data") or "")
    payload["metadata"] = sanitize_metadata(payload.get("metadata") or {})
    return payload


def _safe_event_data(value: Any) -> str:
    text = _redact_log_line(str(value or "").replace("\r", ""))
    max_chars = _bounded_int(getattr(settings, "KUBERNETES_ADMIN_TRANSCRIPT_EVENT_MAX_CHARS", DEFAULT_TRANSCRIPT_EVENT_MAX_CHARS), default=DEFAULT_TRANSCRIPT_EVENT_MAX_CHARS, minimum=100, maximum=20_000)
    if len(text) > max_chars:
        return f"{text[:max_chars]}...[truncated]"
    return text


def _bounded_limit(value: int | str | None) -> int:
    return _bounded_int(value if value is not None else 100, default=100, minimum=1, maximum=500)


def _bounded_int(value: int | str | None, *, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value if value not in (None, "") else default)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(parsed, maximum))
