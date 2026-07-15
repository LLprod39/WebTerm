from __future__ import annotations

import pytest
from django.contrib.auth.models import User

from kubernetes_ops.models import (
    K8sAdminAction,
    K8sAdminRecording,
    K8sAdminRecordingEvent,
    K8sAdminSession,
    K8sCluster,
    K8sProvider,
)
from kubernetes_ops.services.release_evidence import build_kubernetes_release_evidence
from kubernetes_ops.services.release_post_review_retention import (
    build_kubernetes_release_post_review_retention_evidence,
)


@pytest.mark.django_db
def test_release_post_review_retention_evidence_is_transaction_rollback_and_redacted():
    user = User.objects.create_user(username="release-post-review-proof", password="x", is_staff=True)
    initial = {
        "sessions": K8sAdminSession.objects.count(),
        "actions": K8sAdminAction.objects.count(),
        "recordings": K8sAdminRecording.objects.count(),
        "events": K8sAdminRecordingEvent.objects.count(),
        "providers": K8sProvider.objects.count(),
        "clusters": K8sCluster.objects.count(),
    }

    proof = build_kubernetes_release_post_review_retention_evidence(user, True)

    assert proof["status"] == "ready"
    assert proof["mode"] == "transaction_rollback"
    assert proof["checks"]["pending_post_review_detected"] is True
    assert proof["checks"]["post_review_redacted"] is True
    assert proof["checks"]["recording_event_redacted"] is True
    assert proof["checks"]["retention_dry_run_detected_events"] >= 1
    assert proof["checks"]["retention_apply_deleted_events"] >= 1
    assert proof["checks"]["retention_apply_updated_recordings"] >= 1
    assert proof["created"]["actions"] == 1
    assert proof["created"]["recordings"] == 1
    assert proof["created"]["events"] == 0
    assert "release-post-review-token" not in str(proof)
    assert "post-review-secret" not in str(proof)
    assert K8sAdminSession.objects.count() == initial["sessions"]
    assert K8sAdminAction.objects.count() == initial["actions"]
    assert K8sAdminRecording.objects.count() == initial["recordings"]
    assert K8sAdminRecordingEvent.objects.count() == initial["events"]
    assert K8sProvider.objects.count() == initial["providers"]
    assert K8sCluster.objects.count() == initial["clusters"]


@pytest.mark.django_db
def test_release_evidence_blocks_failed_post_review_retention_proof(monkeypatch):
    user = User.objects.create_user(username="release-post-review-fail", password="x", is_staff=True)
    monkeypatch.setattr(
        "kubernetes_ops.services.release_evidence._post_review_retention_evidence",
        lambda _user, _enabled: {"success": False, "status": "failed"},
    )

    evidence = build_kubernetes_release_evidence(
        user=user,
        run_provider_probe=False,
        run_sync_dry_run=False,
        run_mcp_call=False,
        run_action_controls=False,
        run_admin_mode_safety=False,
        run_interactive_transport_evidence=False,
        run_interactive_shell_streams=False,
        run_normal_user_surface=False,
        run_readonly_rbac_live=False,
    )

    assert "post_review_retention:failed" in evidence["blockers"]
