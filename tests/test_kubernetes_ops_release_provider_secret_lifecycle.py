from __future__ import annotations

import pytest
from django.contrib.auth.models import User

from core_ui.managed_secrets import KUBERNETES_PROVIDER_TOKEN_NAMESPACE
from core_ui.models import ManagedSecret
from kubernetes_ops.models import K8sActionRequest, K8sCluster, K8sProvider
from kubernetes_ops.services.release_evidence import build_kubernetes_release_evidence


def _ready_report(ready_for_sidebar: bool = False) -> dict:
    return {
        "success": True,
        "status": "ready" if ready_for_sidebar else "configured",
        "ready_for_sidebar": ready_for_sidebar,
        "summary": {"ready": 12, "missing": 0, "manual": 0, "total": 12},
        "checks": [{"id": "architecture_guard", "status": "ready", "required": True}],
        "worker_state": {"status": "running", "is_stale": False},
        "access_model": {"status": "ready", "native_mutations_enabled": False, "exec_enabled": False},
        "identity_runtime": {"status": "ready", "webterm_login_gateway": {"status": "ready"}},
        "production_gate": {"target_environment": "local", "core_evidence_ready": True},
    }


@pytest.mark.django_db
def test_kubernetes_release_evidence_provider_secret_lifecycle_is_rollback_only(monkeypatch):
    user = User.objects.create_user(username="release-provider-secret-proof", password="x", is_staff=True)
    monkeypatch.setattr(
        "kubernetes_ops.services.release_evidence.build_kubernetes_readiness_report",
        lambda user, **_kwargs: _ready_report(False),
    )
    before_provider_ids = set(K8sProvider.objects.values_list("id", flat=True))
    before_secret_ids = set(
        ManagedSecret.objects.filter(namespace=KUBERNETES_PROVIDER_TOKEN_NAMESPACE).values_list("id", flat=True)
    )

    evidence = build_kubernetes_release_evidence(
        user=user,
        run_provider_probe=False,
        run_sync_dry_run=False,
        run_mcp_call=False,
        run_readonly_rbac_live=False,
    )

    lifecycle = evidence["provider_secret_lifecycle"]
    assert lifecycle["success"] is True
    assert lifecycle["status"] == "ready"
    assert lifecycle["rotation_supported"] is True
    assert lifecycle["persistent_rows"] is False
    assert lifecycle["checks"]["plaintext_not_serialized"] is True
    assert set(K8sProvider.objects.values_list("id", flat=True)) == before_provider_ids
    assert set(ManagedSecret.objects.filter(namespace=KUBERNETES_PROVIDER_TOKEN_NAMESPACE).values_list("id", flat=True)) == before_secret_ids


@pytest.mark.django_db
def test_kubernetes_release_evidence_action_controls_are_rollback_only(monkeypatch):
    user = User.objects.create_user(username="release-action-proof", password="x", is_staff=True)
    monkeypatch.setattr(
        "kubernetes_ops.services.release_evidence.build_kubernetes_readiness_report",
        lambda user, **_kwargs: _ready_report(False),
    )
    action_count = K8sActionRequest.objects.count()
    cluster_count = K8sCluster.objects.count()

    evidence = build_kubernetes_release_evidence(
        user=user,
        run_provider_probe=False,
        run_sync_dry_run=False,
        run_mcp_call=False,
        run_readonly_rbac_live=False,
    )

    assert evidence["action_controls"]["success"] is True
    assert evidence["action_controls"]["persistent_rows"] is False
    assert evidence["action_controls"]["gitops_provider"] == "gitlab"
    assert evidence["action_controls"]["gitops_gitlab_payload_ready"] is True
    assert evidence["action_controls"]["gitops_write_performed"] is False
    assert evidence["action_controls"]["gitops_cluster_mutation_performed"] is False
    assert "fleet_bundle_reconciled" in evidence["action_controls"]["gitops_verification_plan_check_ids"]
    assert K8sActionRequest.objects.count() == action_count
    assert K8sCluster.objects.count() == cluster_count
