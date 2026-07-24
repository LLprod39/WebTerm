from __future__ import annotations

from types import SimpleNamespace

import pytest
from django.contrib.auth.models import User
from django.test import override_settings

from kubernetes_ops.models import K8sAppRef, K8sCluster, K8sProvider
from kubernetes_ops.services.provider_probe import KubernetesProviderProbeResult
from kubernetes_ops.services.release_evidence import build_kubernetes_release_evidence
from kubernetes_ops.services.sync import KubernetesSyncResult
from tests.kubernetes_ops_release_evidence_helpers import (
    PRODUCTION_RELEASE_SETTINGS,
    _grant,
    _ready_action_controls,
    _ready_interactive_transport,
    _ready_preflight,
    _ready_production_action_evidence,
    _ready_rbac_live,
    _ready_report,
)


@pytest.fixture(autouse=True)
def _ready_studio_diagnosis_draft(monkeypatch):
    monkeypatch.setattr(
        "kubernetes_ops.services.release_evidence._studio_diagnosis_draft_evidence",
        lambda _user, _enabled: {"success": True, "status": "ready"},
    )
    monkeypatch.setattr(
        "kubernetes_ops.services.release_evidence._production_action_evidence",
        lambda _enabled: _ready_production_action_evidence(),
    )


@pytest.mark.django_db
def test_kubernetes_release_evidence_redacts_studio_mcp_content_preview(monkeypatch):
    user = User.objects.create_user(username="release-admin-redacted-mcp", password="x", is_staff=True)
    _grant(user, "kubernetes", "studio_pipelines", "studio_mcp")
    provider = K8sProvider.objects.create(
        name="rancher-main",
        kind=K8sProvider.KIND_RANCHER,
        base_url="https://rancher.prod.example.com",
        auth_mode=K8sProvider.AUTH_NONE,
    )
    cluster = K8sCluster.objects.create(name="prod-kz-1", labels={"kube_context": "prod-kz"})
    K8sAppRef.objects.create(name="payments-api", cluster=cluster, namespace="payments", owner=K8sAppRef.OWNER_DEVTRON)

    monkeypatch.setattr(
        "kubernetes_ops.services.release_evidence.build_kubernetes_readiness_report",
        lambda user, **_kwargs: _ready_report(False),
    )
    monkeypatch.setattr(
        "kubernetes_ops.services.release_evidence.probe_kubernetes_provider",
        lambda _provider: KubernetesProviderProbeResult(
            provider_id=provider.id,
            provider_name=provider.name,
            provider_kind=provider.kind,
            success=True,
            status="ready",
            path="/v3/clusters",
        ),
    )
    monkeypatch.setattr(
        "kubernetes_ops.services.release_evidence.sync_kubernetes_providers",
        lambda dry_run: [
            KubernetesSyncResult(
                provider_id=provider.id,
                provider_name=provider.name,
                provider_kind=provider.kind,
                success=True,
                clusters=1,
                dry_run=dry_run,
            )
        ],
    )
    monkeypatch.setattr(
        "kubernetes_ops.services.release_evidence.owned_kubernetes_mcp_server",
        lambda _user: SimpleNamespace(id=7, name="Kubernetes MCP", last_test_ok=True),
    )

    async def fake_call_mcp_tool(_mcp, tool_name, arguments):
        return {
            "content": [{"type": "text", "text": "status ok\npassword=super-secret\nAuthorization: Bearer abc.def"}],
            "structuredContent": {"policy": {"permission_mode": "READ_ONLY", "mutates_state": False}},
        }

    monkeypatch.setattr("kubernetes_ops.services.release_evidence.call_mcp_tool", fake_call_mcp_tool)
    monkeypatch.setattr(
        "kubernetes_ops.services.release_evidence._readonly_rbac_live_evidence", lambda _enabled: _ready_rbac_live()
    )
    monkeypatch.setattr(
        "kubernetes_ops.services.release_evidence.load_kubernetes_release_preflight_artifact",
        lambda: _ready_preflight(),
    )
    monkeypatch.setattr(
        "kubernetes_ops.services.release_evidence.load_kubernetes_interactive_transport_evidence_artifact",
        _ready_interactive_transport,
    )

    with override_settings(**PRODUCTION_RELEASE_SETTINGS):
        evidence = build_kubernetes_release_evidence(user=user)

    assert evidence["production_ready"] is True
    assert evidence["studio_mcp"]["status"] == "ready"
    preview = evidence["studio_mcp"]["content_preview"]
    assert "super-secret" not in preview
    assert "abc.def" not in preview
    assert "[REDACTED:" in preview


@pytest.mark.django_db
def test_kubernetes_release_evidence_redacts_provider_and_sync_payloads(monkeypatch):
    user = User.objects.create_user(username="release-admin-redacted-provider", password="x", is_staff=True)
    provider = K8sProvider.objects.create(
        name="rancher-main",
        kind=K8sProvider.KIND_RANCHER,
        base_url="https://svc-user:provider-secret@rancher.prod.example.com:8443/dashboard?token=raw-url-token",
        auth_mode=K8sProvider.AUTH_NONE,
    )
    monkeypatch.setattr(
        "kubernetes_ops.services.release_evidence.build_kubernetes_readiness_report",
        lambda user, **_kwargs: _ready_report(False),
    )
    monkeypatch.setattr(
        "kubernetes_ops.services.release_evidence.probe_kubernetes_provider",
        lambda _provider: KubernetesProviderProbeResult(
            provider_id=provider.id,
            provider_name=provider.name,
            provider_kind=provider.kind,
            success=False,
            status="error",
            path="https://probe-user:probe-secret@rancher.prod.example.com/v3/clusters?token=probe-url-token",
            error="password=provider-password\nAuthorization: Bearer provider.jwt",
        ),
    )
    monkeypatch.setattr(
        "kubernetes_ops.services.release_evidence.sync_kubernetes_providers",
        lambda dry_run: [
            KubernetesSyncResult(
                provider_id=provider.id,
                provider_name=provider.name,
                provider_kind=provider.kind,
                success=False,
                dry_run=dry_run,
                error="token=sync-secret\nAuthorization: Bearer sync.jwt",
            )
        ],
    )
    monkeypatch.setattr(
        "kubernetes_ops.services.release_evidence.load_kubernetes_release_preflight_artifact",
        lambda: _ready_preflight(),
    )

    evidence = build_kubernetes_release_evidence(
        user=user,
        run_mcp_call=False,
        run_action_controls=False,
        run_readonly_rbac_live=False,
    )

    provider_payload = evidence["provider_probes"][0]
    sync_payload = evidence["sync_dry_run"][0]
    assert provider_payload["provider_base_url"] == "https://rancher.prod.example.com:8443"
    assert provider_payload["path"] == "https://rancher.prod.example.com/v3/clusters"
    serialized = str(evidence)
    for secret in (
        "provider-secret",
        "raw-url-token",
        "probe-secret",
        "probe-url-token",
        "provider-password",
        "provider.jwt",
        "sync-secret",
        "sync.jwt",
    ):
        assert secret not in serialized
    assert "[REDACTED:" in provider_payload["error"]
    assert "[REDACTED:" in sync_payload["error"]
    assert evidence["artifact_safety"]["status"] == "ready"


@pytest.mark.django_db
def test_kubernetes_release_evidence_self_scan_blocks_raw_artifact_leak(monkeypatch):
    user = User.objects.create_user(username="release-admin-artifact-leak", password="x", is_staff=True)
    monkeypatch.setattr(
        "kubernetes_ops.services.release_evidence.build_kubernetes_readiness_report",
        lambda user, **_kwargs: _ready_report(False),
    )
    monkeypatch.setattr(
        "kubernetes_ops.services.release_evidence._provider_probe_evidence",
        lambda _enabled: [
            {"success": True, "status": "ready", "provider_name": "leaky-provider", "token": "raw-provider-token"}
        ],
    )
    monkeypatch.setattr(
        "kubernetes_ops.services.release_evidence._sync_dry_run_evidence",
        lambda _enabled: [{"success": True, "status": "ready", "provider_name": "leaky-provider", "dry_run": True}],
    )
    monkeypatch.setattr(
        "kubernetes_ops.services.release_evidence._studio_mcp_evidence",
        lambda _user, _enabled: {
            "success": True,
            "status": "ready",
            "policy": {"permission_mode": "READ_ONLY", "mutates_state": False},
            "policy_errors": [],
        },
    )
    monkeypatch.setattr(
        "kubernetes_ops.services.release_evidence._action_controls_evidence",
        lambda _user, _enabled: _ready_action_controls(),
    )
    monkeypatch.setattr(
        "kubernetes_ops.services.release_evidence._admin_mode_safety_evidence",
        lambda _user, _enabled: {
            "success": True,
            "status": "ready",
            "provider_called": False,
            "admin_actions_created": 0,
        },
    )
    monkeypatch.setattr(
        "kubernetes_ops.services.release_evidence._readonly_rbac_live_evidence",
        lambda _enabled: _ready_rbac_live(),
    )
    monkeypatch.setattr(
        "kubernetes_ops.services.release_evidence.load_kubernetes_release_preflight_artifact",
        lambda: _ready_preflight(),
    )
    monkeypatch.setattr(
        "kubernetes_ops.services.release_evidence.build_kubernetes_release_scope_report",
        lambda **_kwargs: {"success": True, "status": "ready", "approval_ref_present": True},
    )

    with override_settings(
        KUBERNETES_OPS_RELEASE_ENVIRONMENT="production",
        KUBERNETES_OPS_PRODUCTION_APPROVAL_REF="CHG-K8S-1",
    ):
        evidence = build_kubernetes_release_evidence(user=user)

    assert evidence["production_ready"] is False
    assert "artifact_safety:unsafe" in evidence["blockers"]
    assert evidence["artifact_safety"]["status"] == "unsafe"
    assert evidence["artifact_safety"]["issue_count"] > 0
    assert "raw-provider-token" not in str(evidence["artifact_safety"]["issues"])
    assert (
        "Remove raw secrets or credentialed URLs from release evidence output."
        in evidence["release_summary"]["next_steps"]
    )
