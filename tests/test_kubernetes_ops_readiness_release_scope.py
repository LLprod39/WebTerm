from __future__ import annotations

import pytest
from django.contrib.auth.models import User
from django.test import override_settings

from core_ui.models import UserAppPermission
from kubernetes_ops.models import K8sCluster, K8sProvider
from kubernetes_ops.services import readiness as readiness_service
from kubernetes_ops.services.readiness import build_kubernetes_readiness_report
from studio.models import MCPServerPool


PRODUCTION_REFS = {
    "KUBERNETES_OPS_PRODUCTION_EVIDENCE_REF": "artifact:production-bundle",
    "KUBERNETES_OPS_IDENTITY_RUNTIME_EVIDENCE_REF": "artifact:sso-proof",
    "KUBERNETES_OPS_LIVE_PROVIDER_EVIDENCE_REF": "artifact:provider-proof",
    "KUBERNETES_OPS_READONLY_RBAC_EVIDENCE_REF": "artifact:rbac-proof",
    "KUBERNETES_OPS_KUBERNETES_MCP_EVIDENCE_REF": "artifact:mcp-proof",
    "KUBERNETES_OPS_PRODUCTION_ROLLBACK_EVIDENCE_REF": "artifact:rollback-proof",
    "KUBERNETES_OPS_PRODUCTION_NATIVE_VERIFICATION_EVIDENCE_REF": "artifact:native-verification-proof",
}


def _ready(check_id: str, detail: str = "ok", *, required: bool = True) -> dict:
    return {"id": check_id, "status": "ready", "detail": detail, "required": required}


def _patch_ready_dependencies(monkeypatch, *, release_artifact_status: str = "ready"):
    monkeypatch.setattr(readiness_service, "kubernetes_permission_check", lambda _user: _ready("permission_matrix"))
    monkeypatch.setattr(readiness_service, "kubernetes_access_model_check", lambda: _ready("access_model"))
    monkeypatch.setattr(readiness_service, "kubernetes_identity_runtime_check", lambda: _ready("identity_runtime"))
    monkeypatch.setattr(readiness_service, "_provider_check", lambda kind, _label: _ready(f"{kind}_provider"))
    monkeypatch.setattr(readiness_service, "_provider_health_check", lambda: _ready("provider_health"))
    monkeypatch.setattr(readiness_service, "_sync_worker_check", lambda _worker_state: _ready("sync_worker"))
    monkeypatch.setattr(readiness_service, "_studio_automation_check", lambda _user: _ready("studio_automation", required=False))
    monkeypatch.setattr(readiness_service, "kubernetes_security_review_check", lambda: _ready("security_review", required=False))
    monkeypatch.setattr(readiness_service, "kubernetes_terminal_safety_check", lambda _user: _ready("terminal_exec_threat_model", required=False))
    monkeypatch.setattr(readiness_service, "kubernetes_operator_docs_check", lambda: _ready("operator_docs", required=False))
    monkeypatch.setattr(readiness_service, "kubernetes_frontend_e2e_check", lambda: _ready("frontend_e2e", required=False))
    monkeypatch.setattr(
        readiness_service,
        "build_kubernetes_release_evidence_artifact_report",
        lambda require_ready: {"status": release_artifact_status, "detail": "release artifact check", "required": require_ready},
    )


@pytest.mark.django_db
def test_readiness_keeps_sidebar_locked_for_local_release_scope(monkeypatch):
    user = User.objects.create_user(username="k8s-local-scope", password="password-123")
    K8sCluster.objects.create(name="local")
    _patch_ready_dependencies(monkeypatch)

    with override_settings(
        KUBERNETES_OPS_READY_FOR_SIDEBAR=True,
        KUBERNETES_OPS_RELEASE_ENVIRONMENT="local",
        KUBERNETES_OPS_PRODUCTION_APPROVAL_REF="",
    ):
        report = build_kubernetes_readiness_report(user=user)

    checks = {item["id"]: item for item in report["checks"]}
    assert report["ready_for_sidebar"] is False
    assert report["status"] == "not_configured"
    assert checks["sidebar_release_scope"]["status"] == "missing"
    assert "not production" in checks["sidebar_release_scope"]["detail"]


@pytest.mark.django_db
def test_readiness_allows_sidebar_only_for_approved_production_scope(monkeypatch):
    user = User.objects.create_user(username="k8s-prod-scope", password="password-123")
    K8sCluster.objects.create(name="prod-kz")
    _patch_ready_dependencies(monkeypatch)

    with override_settings(
        KUBERNETES_OPS_READY_FOR_SIDEBAR=True,
        KUBERNETES_OPS_RELEASE_ENVIRONMENT="production",
        KUBERNETES_OPS_PRODUCTION_APPROVAL_REF="CHG-K8S-1",
        **PRODUCTION_REFS,
    ):
        report = build_kubernetes_readiness_report(user=user)

    checks = {item["id"]: item for item in report["checks"]}
    assert report["ready_for_sidebar"] is True
    assert report["status"] == "ready"
    assert checks["sidebar_release_scope"]["status"] == "ready"
    assert checks["release_evidence_artifact"]["status"] == "ready"
    assert checks["release_evidence_artifact"]["required"] is True
    assert report["production_gate"]["core_evidence_ready"] is True
    assert report["production_gate"]["missing_reference_count"] == 0


@pytest.mark.django_db
def test_readiness_blocks_approved_production_scope_when_providers_are_local(monkeypatch):
    user = User.objects.create_user(username="k8s-prod-local-provider", password="password-123")
    K8sCluster.objects.create(name="prod-kz")
    K8sProvider.objects.create(
        name="rancher-main",
        kind=K8sProvider.KIND_RANCHER,
        base_url="https://host.docker.internal:8443",
        auth_mode=K8sProvider.AUTH_NONE,
        enabled=True,
    )
    _patch_ready_dependencies(monkeypatch)

    with override_settings(
        KUBERNETES_OPS_READY_FOR_SIDEBAR=True,
        KUBERNETES_OPS_RELEASE_ENVIRONMENT="production",
        KUBERNETES_OPS_PRODUCTION_APPROVAL_REF="CHG-K8S-1",
        **PRODUCTION_REFS,
    ):
        report = build_kubernetes_readiness_report(user=user)

    checks = {item["id"]: item for item in report["checks"]}
    assert report["ready_for_sidebar"] is False
    assert report["status"] == "not_configured"
    assert checks["sidebar_release_scope"]["status"] == "missing"
    assert "provider.base_url=[local-url]" in checks["sidebar_release_scope"]["detail"]
    assert "https://host.docker.internal:8443" not in str(report["production_gate"])


@pytest.mark.django_db
def test_readiness_blocks_sidebar_when_release_evidence_artifact_is_not_ready(monkeypatch):
    user = User.objects.create_user(username="k8s-prod-stale-artifact", password="password-123")
    K8sCluster.objects.create(name="prod-kz")
    _patch_ready_dependencies(monkeypatch, release_artifact_status="missing")

    with override_settings(
        KUBERNETES_OPS_READY_FOR_SIDEBAR=True,
        KUBERNETES_OPS_RELEASE_ENVIRONMENT="production",
        KUBERNETES_OPS_PRODUCTION_APPROVAL_REF="CHG-K8S-1",
        **PRODUCTION_REFS,
    ):
        report = build_kubernetes_readiness_report(user=user)

    checks = {item["id"]: item for item in report["checks"]}
    assert report["ready_for_sidebar"] is False
    assert report["status"] == "not_configured"
    assert checks["sidebar_release_scope"]["status"] == "ready"
    assert checks["release_evidence_artifact"]["status"] == "missing"
    assert checks["release_evidence_artifact"]["required"] is True


@pytest.mark.django_db
def test_readiness_blocks_sidebar_when_production_core_refs_are_missing(monkeypatch):
    user = User.objects.create_user(username="k8s-prod-missing-refs", password="password-123")
    K8sCluster.objects.create(name="prod-kz")
    _patch_ready_dependencies(monkeypatch)

    with override_settings(
        KUBERNETES_OPS_READY_FOR_SIDEBAR=True,
        KUBERNETES_OPS_RELEASE_ENVIRONMENT="production",
        KUBERNETES_OPS_PRODUCTION_APPROVAL_REF="CHG-K8S-1",
    ):
        report = build_kubernetes_readiness_report(user=user)

    checks = {item["id"]: item for item in report["checks"]}
    assert report["ready_for_sidebar"] is False
    assert report["status"] == "not_configured"
    assert checks["sidebar_release_scope"]["status"] == "missing"
    assert "KUBERNETES_OPS_PRODUCTION_EVIDENCE_REF" in checks["sidebar_release_scope"]["detail"]
    assert report["production_gate"]["core_evidence_ready"] is False
    assert report["production_gate"]["missing_reference_count"] >= 1


@pytest.mark.django_db
def test_readiness_blocks_approved_production_scope_when_kubernetes_mcp_is_local(monkeypatch):
    user = User.objects.create_user(username="k8s-prod-local-mcp", password="password-123")
    UserAppPermission.objects.create(user=user, feature="studio_mcp", allowed=True)
    K8sCluster.objects.create(name="prod-kz")
    MCPServerPool.objects.create(
        owner=user,
        name="Kubernetes MCP",
        transport=MCPServerPool.TRANSPORT_SSE,
        url="http://mcp-demo:8765/mcp",
        last_test_ok=True,
    )
    _patch_ready_dependencies(monkeypatch)

    with override_settings(
        KUBERNETES_OPS_READY_FOR_SIDEBAR=True,
        KUBERNETES_OPS_RELEASE_ENVIRONMENT="production",
        KUBERNETES_OPS_PRODUCTION_APPROVAL_REF="CHG-K8S-1",
        **PRODUCTION_REFS,
    ):
        report = build_kubernetes_readiness_report(user=user)

    checks = {item["id"]: item for item in report["checks"]}
    assert report["ready_for_sidebar"] is False
    assert report["status"] == "not_configured"
    assert checks["sidebar_release_scope"]["status"] == "missing"
    assert "studio_mcp.url=[local-url]" in checks["sidebar_release_scope"]["detail"]
    assert "http://mcp-demo:8765/mcp" not in str(report["production_gate"])
