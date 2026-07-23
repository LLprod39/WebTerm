from __future__ import annotations

import pytest
from django.contrib.auth.models import User

from kubernetes_ops.services.release_evidence import build_kubernetes_release_evidence


def _ready_report(ready_for_sidebar: bool) -> dict:
    return {
        "success": True,
        "status": "ready" if ready_for_sidebar else "configured",
        "ready_for_sidebar": ready_for_sidebar,
        "summary": {"ready": 12, "missing": 0, "manual": 0, "total": 12},
        "checks": [{"id": "architecture_guard", "status": "ready", "detail": "ok", "required": True}],
        "worker_state": {"status": "running", "is_stale": False},
        "access_model": {"status": "ready", "native_mutations_enabled": False, "exec_enabled": False},
        "identity_runtime": {"status": "ready", "identity_provider": "Keycloak/OIDC", "enforced": True},
        "production_gate": {
            "target_environment": "production",
            "core_evidence_ready": True,
            "missing_reference_count": 0,
        },
    }


def _ready_rbac_live(context: str = "prod-kz") -> dict:
    return {
        "success": True,
        "status": "ready",
        "context": context,
        "applied": True,
        "service_account": "system:serviceaccount:webterm-system:webterm-kubernetes-readonly",
        "allowed_count": 7,
        "denied_count": 7,
        "errors": [],
    }


def _ready_production_action_evidence() -> dict:
    return {
        "success": True,
        "status": "ready",
        "summary": {"blocked_action_class_count": 11},
        "coverage": {"blocked_action_contract_complete": True},
    }


@pytest.fixture(autouse=True)
def _ready_release_runtime(monkeypatch):
    monkeypatch.setattr(
        "kubernetes_ops.services.release_evidence._studio_diagnosis_draft_evidence",
        lambda _user, _enabled: {"success": True, "status": "ready"},
    )
    monkeypatch.setattr(
        "kubernetes_ops.services.release_evidence._production_action_evidence",
        lambda _enabled: _ready_production_action_evidence(),
    )


@pytest.mark.django_db
def test_kubernetes_release_evidence_reports_runtime_flag_without_blocking_artifact(monkeypatch):
    user = User.objects.create_user(username="release-admin-locked", password="x", is_staff=True)
    monkeypatch.setattr(
        "kubernetes_ops.services.release_evidence.build_kubernetes_readiness_report",
        lambda user, **_kwargs: _ready_report(False),
    )
    monkeypatch.setattr(
        "kubernetes_ops.services.release_evidence._readonly_rbac_live_evidence",
        lambda _enabled: _ready_rbac_live("kind-webterm-k8s"),
    )

    evidence = build_kubernetes_release_evidence(
        user=user,
        run_provider_probe=False,
        run_sync_dry_run=False,
        run_mcp_call=False,
        run_readonly_rbac_live=False,
    )

    assert evidence["production_ready"] is False
    assert evidence["action_controls"]["status"] == "ready"
    assert "release_scope:local" in evidence["blockers"]
    assert "sidebar_env:KUBERNETES_OPS_READY_FOR_SIDEBAR is not enabled" not in evidence["blockers"]
    assert evidence["enablement"]["env_flag_required"] is True
    assert "provider_probe:provider probe skipped=skipped" in evidence["blockers"]
    assert evidence["release_summary"]["status"] == "blocked"
    assert evidence["release_summary"]["top_blockers"][:2] == [
        "provider_probe:provider probe skipped=skipped",
        "sync_dry_run:sync dry-run skipped=failed",
    ]
    assert "Run release evidence in production" in evidence["release_summary"]["next_steps"][0]


@pytest.mark.django_db
def test_kubernetes_release_evidence_blocks_missing_production_action_evidence(monkeypatch):
    user = User.objects.create_user(username="release-admin-missing-action-proof", password="x", is_staff=True)
    monkeypatch.setattr(
        "kubernetes_ops.services.release_evidence.build_kubernetes_readiness_report",
        lambda user, **_kwargs: _ready_report(False),
    )
    monkeypatch.setattr(
        "kubernetes_ops.services.release_evidence._production_action_evidence",
        lambda _enabled: {
            "success": False,
            "status": "missing",
            "errors": ["production action evidence artifact is missing"],
        },
    )

    evidence = build_kubernetes_release_evidence(
        user=user,
        run_provider_probe=False,
        run_sync_dry_run=False,
        run_mcp_call=False,
        run_readonly_rbac_live=False,
    )

    assert evidence["production_ready"] is False
    assert "production_action_evidence:missing" in evidence["blockers"]
    assert evidence["release_summary"]["production_action_evidence_status"] == "missing"
    assert any(
        step.startswith("Regenerate production action evidence") for step in evidence["release_summary"]["next_steps"]
    )
