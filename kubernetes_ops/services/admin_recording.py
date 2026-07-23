from __future__ import annotations

from datetime import timedelta
from typing import Any

from django.conf import settings
from django.db.models import Count
from django.utils import timezone

from kubernetes_ops.models import K8sAdminAction, K8sAdminRecording, K8sAdminRecordingEvent, K8sAdminSession
from kubernetes_ops.services.admin_resources import AdminResourceError
from kubernetes_ops.services.describe import sanitize_metadata
from kubernetes_ops.services.logs import _redact_log_line

DEFAULT_METADATA_RETENTION_DAYS = 365
DEFAULT_TRANSCRIPT_RETENTION_DAYS = 30
DEFAULT_TRANSCRIPT_EVENT_MAX_CHARS = 2_000
DEFAULT_TRANSCRIPT_EVENT_MAX_COUNT = 2_000
MAX_RECORDING_RETENTION_DAYS = 3650

INTERACTIVE_RECORDING_SETTINGS = {
    "exec": "KUBERNETES_ADMIN_EXEC_RECORDING_ENABLED",
    "port_forward": "KUBERNETES_ADMIN_PORT_FORWARD_RECORDING_ENABLED",
    "cluster_terminal": "KUBERNETES_ADMIN_CLUSTER_TERMINAL_RECORDING_ENABLED",
    "node_debug": "KUBERNETES_ADMIN_NODE_DEBUG_RECORDING_ENABLED",
}


def interactive_recording_policy(
    operation: str, *, requires_transcript: bool, payload_stored: bool = False
) -> dict[str, Any]:
    operation_value = str(operation or "").strip()
    enabled = recording_enabled(operation_value)
    return {
        "operation": operation_value,
        "required": True,
        "enabled": enabled,
        "mode": "metadata_only" if not requires_transcript else "transcript_required",
        "metadata_retention_days": _retention_days(
            "KUBERNETES_ADMIN_INTERACTIVE_METADATA_RETENTION_DAYS", DEFAULT_METADATA_RETENTION_DAYS
        ),
        "transcript_retention_days": _retention_days(
            "KUBERNETES_ADMIN_INTERACTIVE_TRANSCRIPT_RETENTION_DAYS", DEFAULT_TRANSCRIPT_RETENTION_DAYS
        ),
        "transcript_required_before_transport": bool(requires_transcript),
        "stdin_recording_required": bool(requires_transcript),
        "stdout_recording_required": bool(requires_transcript),
        "payload_stored": bool(payload_stored),
    }


def recording_enabled(operation: str) -> bool:
    setting_name = INTERACTIVE_RECORDING_SETTINGS.get(str(operation or "").strip(), "")
    return bool(setting_name and getattr(settings, setting_name, False))


def require_interactive_recording(operation: str) -> dict[str, Any]:
    policy = interactive_recording_policy(
        operation, requires_transcript=operation in {"exec", "cluster_terminal", "node_debug"}
    )
    if policy["enabled"]:
        return policy
    raise AdminResourceError(
        f"Kubernetes {operation.replace('_', ' ')} recording is required before provider transport can start.",
        code=f"{operation}_recording_required",
        status=403,
        payload={"recording_policy": policy},
    )


def create_interactive_recording(
    *,
    user,
    session: K8sAdminSession,
    action: K8sAdminAction,
    operation: str,
    policy: dict[str, Any],
    status: str = K8sAdminRecording.STATUS_ACTIVE,
    summary: dict[str, Any] | None = None,
) -> K8sAdminRecording:
    now = timezone.now()
    metadata_retention_days = _retention_from_policy(policy, "metadata_retention_days", DEFAULT_METADATA_RETENTION_DAYS)
    transcript_retention_days = _retention_from_policy(
        policy, "transcript_retention_days", DEFAULT_TRANSCRIPT_RETENTION_DAYS
    )
    transcript_required = bool(policy.get("transcript_required_before_transport"))
    return K8sAdminRecording.objects.create(
        session=session,
        action=action,
        user=user,
        username_snapshot=getattr(user, "username", ""),
        cluster=action.cluster,
        namespace=action.namespace,
        resource_kind=action.resource_kind,
        resource_name=action.resource_name,
        operation=str(operation or "").strip(),
        status=status,
        mode=str(policy.get("mode") or "metadata_only")[:40],
        transcript_required=transcript_required,
        transcript_stored=False,
        payload_stored=bool(policy.get("payload_stored")),
        stdin_recording_required=bool(policy.get("stdin_recording_required")),
        stdout_recording_required=bool(policy.get("stdout_recording_required")),
        metadata_retention_days=metadata_retention_days,
        transcript_retention_days=transcript_retention_days,
        metadata_delete_after=now + timedelta(days=metadata_retention_days),
        transcript_delete_after=now + timedelta(days=transcript_retention_days) if transcript_required else None,
        policy_snapshot=sanitize_metadata(policy),
        summary=sanitize_metadata(summary or {}),
        started_at=now,
        finished_at=now
        if status
        in {K8sAdminRecording.STATUS_BLOCKED, K8sAdminRecording.STATUS_COMPLETED, K8sAdminRecording.STATUS_FAILED}
        else None,
    )


def recording_public_payload(recording: K8sAdminRecording | None) -> dict[str, Any]:
    if recording is None:
        return {}
    return {
        "id": str(recording.recording_id),
        "operation": recording.operation,
        "status": recording.status,
        "mode": recording.mode,
        "transcript_required": recording.transcript_required,
        "transcript_stored": recording.transcript_stored,
        "payload_stored": recording.payload_stored,
        "event_count": recording.events.count(),
        "metadata_retention_days": recording.metadata_retention_days,
        "transcript_retention_days": recording.transcript_retention_days,
        "metadata_delete_after": recording.metadata_delete_after.isoformat()
        if recording.metadata_delete_after
        else None,
        "transcript_delete_after": recording.transcript_delete_after.isoformat()
        if recording.transcript_delete_after
        else None,
    }


def finish_interactive_recording_for_action(
    *, action: K8sAdminAction, status: str, summary: dict[str, Any]
) -> K8sAdminRecording | None:
    recording = action.recordings.order_by("-created_at", "-id").first()
    if recording is None:
        return None
    recording.status = status
    recording.summary = sanitize_metadata(summary)
    recording.transcript_stored = bool(summary.get("transcript_stored")) or recording.events.exists()
    recording.payload_stored = bool(summary.get("payload_stored"))
    recording.finished_at = timezone.now()
    recording.save(
        update_fields=["status", "summary", "transcript_stored", "payload_stored", "finished_at", "updated_at"]
    )
    return recording


def append_interactive_recording_event(
    *,
    recording_pk: int,
    stream: str,
    data: str,
    sequence: int = 0,
    metadata: dict[str, Any] | None = None,
) -> K8sAdminRecordingEvent | None:
    recording = K8sAdminRecording.objects.filter(pk=recording_pk).first()
    if recording is None or not recording.transcript_required:
        return None
    if recording.events.count() >= _bounded_setting(
        "KUBERNETES_ADMIN_TRANSCRIPT_EVENT_MAX_COUNT", DEFAULT_TRANSCRIPT_EVENT_MAX_COUNT, minimum=1, maximum=10_000
    ):
        recording.summary = sanitize_metadata({**(recording.summary or {}), "transcript_event_truncated": True})
        recording.save(update_fields=["summary", "updated_at"])
        return None
    stream_value = str(stream or "").strip().lower()
    if stream_value not in {
        K8sAdminRecordingEvent.STREAM_STDIN,
        K8sAdminRecordingEvent.STREAM_STDOUT,
        K8sAdminRecordingEvent.STREAM_STDERR,
        K8sAdminRecordingEvent.STREAM_STATUS,
    }:
        stream_value = K8sAdminRecordingEvent.STREAM_STATUS
    original = str(data or "")
    redacted_text, truncated = _safe_transcript_text(original)
    event = K8sAdminRecordingEvent.objects.create(
        recording=recording,
        sequence=max(0, int(sequence or 0)),
        stream=stream_value,
        data=redacted_text,
        original_length=len(original),
        stored_length=len(redacted_text),
        redacted=redacted_text != original,
        truncated=truncated,
        metadata=sanitize_metadata(metadata or {}),
    )
    if not recording.transcript_stored:
        recording.transcript_stored = True
        recording.save(update_fields=["transcript_stored", "updated_at"])
    return event


def serialize_recording_event(event: K8sAdminRecordingEvent) -> dict[str, Any]:
    return {
        "id": event.id,
        "recording_id": str(event.recording.recording_id),
        "sequence": event.sequence,
        "stream": event.stream,
        "data": event.data,
        "original_length": event.original_length,
        "stored_length": event.stored_length,
        "redacted": event.redacted,
        "truncated": event.truncated,
        "metadata": sanitize_metadata(event.metadata or {}),
        "created_at": event.created_at.isoformat() if event.created_at else None,
    }


def recording_retention_inventory(*, now=None) -> dict[str, Any]:
    current_time = now or timezone.now()
    metadata_expired = _metadata_expired_recordings(current_time)
    transcript_expired = _transcript_expired_recordings(current_time).exclude(pk__in=metadata_expired.values("pk"))
    active = K8sAdminRecording.objects.exclude(pk__in=metadata_expired.values("pk"))
    return {
        "now": current_time.isoformat(),
        "summary": {
            "metadata_expired_count": metadata_expired.count(),
            "transcript_expired_count": transcript_expired.count(),
            "transcript_event_expired_count": K8sAdminRecordingEvent.objects.filter(
                recording__in=transcript_expired
            ).count(),
            "active_recording_count": active.count(),
            "total_recording_count": K8sAdminRecording.objects.count(),
            "total_event_count": K8sAdminRecordingEvent.objects.count(),
        },
        "metadata_expired_by_operation": _recording_counts_by_operation(metadata_expired),
        "transcript_expired_by_operation": _recording_counts_by_operation(transcript_expired),
    }


def cleanup_interactive_recordings(*, dry_run: bool = True, batch_size: int = 1000, now=None) -> dict[str, Any]:
    current_time = now or timezone.now()
    size = max(1, min(int(batch_size or 1000), 5000))
    metadata_expired = _metadata_expired_recordings(current_time).order_by("id")
    transcript_expired = (
        _transcript_expired_recordings(current_time).exclude(pk__in=metadata_expired.values("pk")).order_by("id")
    )
    metadata_expired_count = metadata_expired.count()
    transcript_expired_count = transcript_expired.count()
    transcript_event_expired_count = K8sAdminRecordingEvent.objects.filter(recording__in=transcript_expired).count()
    metadata_expired_by_operation = _recording_counts_by_operation(metadata_expired)
    transcript_expired_by_operation = _recording_counts_by_operation(transcript_expired)
    metadata_deleted_count = 0
    transcript_event_deleted_count = 0
    transcript_recordings_updated_count = 0

    if not dry_run:
        transcript_ids = list(transcript_expired.values_list("id", flat=True))
        if transcript_ids:
            transcript_event_deleted_count, _ = K8sAdminRecordingEvent.objects.filter(
                recording_id__in=transcript_ids
            ).delete()
            cleaned_at = current_time.isoformat()
            for recording in (
                K8sAdminRecording.objects.filter(id__in=transcript_ids).order_by("id").iterator(chunk_size=size)
            ):
                recording.transcript_stored = False
                recording.summary = sanitize_metadata(
                    {
                        **(recording.summary or {}),
                        "transcript_retention_cleaned_at": cleaned_at,
                    }
                )
                recording.save(update_fields=["transcript_stored", "summary", "updated_at"])
                transcript_recordings_updated_count += 1
        while True:
            metadata_ids = list(metadata_expired.values_list("id", flat=True)[:size])
            if not metadata_ids:
                break
            K8sAdminRecording.objects.filter(id__in=metadata_ids).delete()
            metadata_deleted_count += len(metadata_ids)

    return {
        "dry_run": bool(dry_run),
        "now": current_time.isoformat(),
        "metadata_expired_count": metadata_expired_count,
        "metadata_deleted_count": metadata_deleted_count,
        "transcript_expired_count": transcript_expired_count,
        "transcript_event_expired_count": transcript_event_expired_count,
        "transcript_event_deleted_count": transcript_event_deleted_count,
        "transcript_recordings_updated_count": transcript_recordings_updated_count,
        "active_recording_count": K8sAdminRecording.objects.count(),
        "active_event_count": K8sAdminRecordingEvent.objects.count(),
        "metadata_expired_by_operation": metadata_expired_by_operation,
        "transcript_expired_by_operation": transcript_expired_by_operation,
    }


def _retention_days(setting_name: str, default: int) -> int:
    try:
        value = int(getattr(settings, setting_name, default) or default)
    except (TypeError, ValueError):
        value = default
    return max(1, min(value, MAX_RECORDING_RETENTION_DAYS))


def _retention_from_policy(policy: dict[str, Any], key: str, default: int) -> int:
    try:
        value = int(policy.get(key) or default)
    except (TypeError, ValueError):
        value = default
    return max(1, min(value, MAX_RECORDING_RETENTION_DAYS))


def _metadata_expired_recordings(now):
    return K8sAdminRecording.objects.filter(metadata_delete_after__isnull=False, metadata_delete_after__lt=now)


def _transcript_expired_recordings(now):
    return K8sAdminRecording.objects.filter(
        transcript_delete_after__isnull=False, transcript_delete_after__lt=now, events__isnull=False
    ).distinct()


def _recording_counts_by_operation(queryset) -> list[dict[str, Any]]:
    return [
        {"operation": str(row["operation"] or ""), "count": int(row["count"] or 0)}
        for row in queryset.values("operation").annotate(count=Count("id")).order_by("operation")
    ]


def _safe_transcript_text(value: str) -> tuple[str, bool]:
    max_chars = _bounded_setting(
        "KUBERNETES_ADMIN_TRANSCRIPT_EVENT_MAX_CHARS", DEFAULT_TRANSCRIPT_EVENT_MAX_CHARS, minimum=100, maximum=20_000
    )
    text = _redact_log_line(str(value or "").replace("\r", ""))
    truncated = len(text) > max_chars
    if truncated:
        text = f"{text[:max_chars]}...[truncated]"
    return text, truncated


def _bounded_setting(setting_name: str, default: int, *, minimum: int, maximum: int) -> int:
    try:
        value = int(getattr(settings, setting_name, default) or default)
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(value, maximum))
