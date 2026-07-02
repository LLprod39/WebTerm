from __future__ import annotations

from datetime import timedelta
from typing import Any

from django.db import transaction
from django.utils import timezone

from app.egress_redaction import redact_egress_text
from core_ui.models import UserAppPermission
from kubernetes_ops.models import K8sAdminAction, K8sAdminRecording, K8sAdminRecordingEvent, K8sAdminSession, K8sCluster, K8sProvider
from kubernetes_ops.services.admin_action_review_readiness import build_admin_action_post_review_report
from kubernetes_ops.services.admin_recording import (
    append_interactive_recording_event,
    cleanup_interactive_recordings,
    create_interactive_recording,
    interactive_recording_policy,
    recording_retention_inventory,
)
from kubernetes_ops.services.describe import sanitize_metadata


def build_kubernetes_release_post_review_retention_evidence(user, enabled: bool) -> dict[str, Any]:
    if not enabled:
        return {"success": False, "status": "skipped", "reason": "post-review and retention proof skipped"}
    if not user or not getattr(user, "is_staff", False):
        return {"success": False, "status": "missing", "reason": "staff user is required for post-review and retention proof"}
    try:
        with transaction.atomic():
            _grant_features(user)
            initial = _counts()
            provider = K8sProvider.objects.create(
                name="release-post-review-rancher",
                kind=K8sProvider.KIND_RANCHER,
                base_url="https://rancher.release-post-review.example.test",
                auth_mode=K8sProvider.AUTH_NONE,
            )
            cluster = K8sCluster.objects.create(
                name="release-post-review",
                environment="test",
                rancher_provider=provider,
                rancher_cluster_id="c-release-post-review",
            )
            proof = _run_checks(user=user, cluster=cluster, initial=initial)
            transaction.set_rollback(True)
            return proof
    except Exception as exc:
        return {"success": False, "status": "error", "error": str(exc)}


def _run_checks(*, user, cluster: K8sCluster, initial: dict[str, int]) -> dict[str, Any]:
    now = timezone.now()
    session = _session(user=user, cluster=cluster)
    action = _action(user=user, session=session, cluster=cluster)
    recording = _recording(user=user, session=session, action=action, now=now)
    event = append_interactive_recording_event(
        recording_pk=recording.pk,
        stream=K8sAdminRecordingEvent.STREAM_STDOUT,
        data="TOKEN=release-post-review-token",
        sequence=1,
    )

    pending_report = build_admin_action_post_review_report()
    pending_found = _pending_contains(pending_report, action)
    post_review = _post_review_payload(user)
    action.response_summary = {**(action.response_summary or {}), "post_review_status": "completed", "post_review": post_review}
    action.save(update_fields=["response_summary", "updated_at"])
    completed_report = build_admin_action_post_review_report()

    inventory = recording_retention_inventory(now=now)
    dry_run = cleanup_interactive_recordings(dry_run=True, now=now)
    cleanup = cleanup_interactive_recordings(dry_run=False, now=now)
    recording.refresh_from_db()

    counts = _counts()
    created = {key: counts[key] - initial[key] for key in initial}
    event_redacted = bool(event and event.redacted and "release-post-review-token" not in event.data)
    post_review_redacted = "post-review-secret" not in str(post_review)
    cleanup_ok = (
        dry_run["transcript_event_expired_count"] >= 1
        and cleanup["transcript_event_deleted_count"] >= 1
        and cleanup["transcript_recordings_updated_count"] >= 1
        and not recording.events.exists()
        and recording.transcript_stored is False
    )
    success = (
        pending_found
        and post_review_redacted
        and event_redacted
        and cleanup_ok
        and created["actions"] == 1
        and created["recordings"] == 1
        and created["events"] == 0
    )
    return {
        "success": success,
        "status": "ready" if success else "failed",
        "mode": "transaction_rollback",
        "checks": {
            "pending_post_review_detected": pending_found,
            "post_review_redacted": post_review_redacted,
            "recording_event_redacted": event_redacted,
            "retention_dry_run_detected_events": dry_run["transcript_event_expired_count"],
            "retention_apply_deleted_events": cleanup["transcript_event_deleted_count"],
            "retention_apply_updated_recordings": cleanup["transcript_recordings_updated_count"],
        },
        "created": created,
        "pending_summary": pending_report.get("summary", {}),
        "completed_summary": completed_report.get("summary", {}),
        "retention_summary": inventory.get("summary", {}),
        "persistent_rows": False,
    }


def _grant_features(user) -> None:
    for feature in ("kubernetes", "kubernetes_break_glass"):
        UserAppPermission.objects.update_or_create(user=user, feature=feature, defaults={"allowed": True})


def _session(*, user, cluster: K8sCluster) -> K8sAdminSession:
    return K8sAdminSession.objects.create(
        user=user,
        username_snapshot=getattr(user, "username", ""),
        cluster=cluster,
        namespace="payments",
        mode=K8sAdminSession.MODE_BREAK_GLASS,
        status=K8sAdminSession.STATUS_CLOSED,
        risk_tier=K8sAdminSession.RISK_CRITICAL,
        reason="release post-review retention proof",
        approval_ref="REL-POST-REVIEW",
        approved_by=user,
        approved_at=timezone.now(),
        closed_at=timezone.now(),
        allowed_verbs=["exec"],
        allowed_kinds=["pod"],
        allowed_namespaces=["payments"],
        expires_at=timezone.now() + timedelta(minutes=15),
    )


def _action(*, user, session: K8sAdminSession, cluster: K8sCluster) -> K8sAdminAction:
    return K8sAdminAction.objects.create(
        session=session,
        user=user,
        username_snapshot=getattr(user, "username", ""),
        cluster=cluster,
        namespace="payments",
        resource_api_version="v1",
        resource_kind="Pod",
        resource_name="payments-api",
        verb=K8sAdminAction.VERB_EXEC,
        status=K8sAdminAction.STATUS_COMPLETED,
        response_summary={},
    )


def _recording(*, user, session: K8sAdminSession, action: K8sAdminAction, now) -> K8sAdminRecording:
    policy = interactive_recording_policy(K8sAdminRecording.OP_EXEC, requires_transcript=True)
    recording = create_interactive_recording(
        user=user,
        session=session,
        action=action,
        operation=K8sAdminRecording.OP_EXEC,
        policy=policy,
        status=K8sAdminRecording.STATUS_COMPLETED,
        summary={"close_reason": "release_retention_proof"},
    )
    recording.transcript_stored = True
    recording.metadata_delete_after = now + timedelta(days=1)
    recording.transcript_delete_after = now - timedelta(seconds=1)
    recording.save(update_fields=["transcript_stored", "metadata_delete_after", "transcript_delete_after", "updated_at"])
    return recording


def _post_review_payload(user) -> dict[str, Any]:
    return sanitize_metadata(
        {
            "outcome": "verified",
            "summary": redact_egress_text("checked TOKEN=post-review-secret").text,
            "reviewed_by": getattr(user, "username", ""),
            "reviewed_at": timezone.now().isoformat(),
        }
    )


def _pending_contains(report: dict[str, Any], action: K8sAdminAction) -> bool:
    return any(str(item.get("action_id") or "") == str(action.action_id) for item in report.get("pending_actions") or [])


def _counts() -> dict[str, int]:
    return {
        "sessions": K8sAdminSession.objects.count(),
        "actions": K8sAdminAction.objects.count(),
        "recordings": K8sAdminRecording.objects.count(),
        "events": K8sAdminRecordingEvent.objects.count(),
        "providers": K8sProvider.objects.count(),
        "clusters": K8sCluster.objects.count(),
    }
