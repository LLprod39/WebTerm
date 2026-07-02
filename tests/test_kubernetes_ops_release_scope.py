from __future__ import annotations

from django.test import override_settings

from kubernetes_ops.services.release_scope import build_kubernetes_release_scope_report


def test_release_scope_blocks_local_kind_evidence_for_production():
    with override_settings(KUBERNETES_OPS_RELEASE_ENVIRONMENT="production", KUBERNETES_OPS_PRODUCTION_APPROVAL_REF="CHG-123"):
        report = build_kubernetes_release_scope_report(
            provider_probes=[
                {
                    "provider_name": "rancher-main",
                    "provider_base_url": "https://host.docker.internal:8443",
                    "status": "ready",
                    "success": True,
                }
            ],
            sync_dry_run=[{"provider_name": "local-devtron-real", "provider_kind": "devtron", "success": True}],
            readonly_rbac_live={
                "success": True,
                "status": "ready",
                "context": "kind-webterm-k8s",
                "service_account": "system:serviceaccount:webterm-system:webterm-kubernetes-readonly",
            },
        )

    assert report["success"] is False
    assert report["status"] == "local_evidence"
    assert report["core_evidence_ready"] is False
    assert report["missing_reference_count"] >= 1
    assert report["local_indicator_count"] >= 2
    assert any(item["source"] == "readonly_rbac_live.context" for item in report["local_indicators"])
    assert any(item["source"] == "provider_probe.provider_base_url" for item in report["local_indicators"])


def test_release_scope_requires_production_approval_ref():
    with override_settings(KUBERNETES_OPS_RELEASE_ENVIRONMENT="production", KUBERNETES_OPS_PRODUCTION_APPROVAL_REF=""):
        report = build_kubernetes_release_scope_report(
            provider_probes=[{"provider_name": "rancher-prod", "status": "ready", "success": True}],
            sync_dry_run=[{"provider_name": "devtron-prod", "provider_kind": "devtron", "success": True}],
            readonly_rbac_live={
                "success": True,
                "status": "ready",
                "context": "prod-kz",
                "service_account": "system:serviceaccount:webterm-system:webterm-kubernetes-readonly",
            },
        )

    assert report["success"] is False
    assert report["status"] == "missing_approval"
    assert any(item["setting"] == "KUBERNETES_OPS_PRODUCTION_APPROVAL_REF" for item in report["missing_required_references"])


def test_release_scope_allows_approved_nonlocal_production_evidence():
    with override_settings(
        KUBERNETES_OPS_RELEASE_ENVIRONMENT="production",
        KUBERNETES_OPS_PRODUCTION_APPROVAL_REF="CHG-123",
        KUBERNETES_OPS_PRODUCTION_EVIDENCE_REF="artifact:production-bundle",
        KUBERNETES_OPS_IDENTITY_RUNTIME_EVIDENCE_REF="artifact:sso-proof",
        KUBERNETES_OPS_LIVE_PROVIDER_EVIDENCE_REF="artifact:provider-proof",
        KUBERNETES_OPS_READONLY_RBAC_EVIDENCE_REF="artifact:rbac-proof",
        KUBERNETES_OPS_KUBERNETES_MCP_EVIDENCE_REF="artifact:mcp-proof",
        KUBERNETES_OPS_PRODUCTION_ROLLBACK_EVIDENCE_REF="artifact:rollback-proof",
        KUBERNETES_OPS_PRODUCTION_NATIVE_VERIFICATION_EVIDENCE_REF="artifact:native-verification-proof",
    ):
        report = build_kubernetes_release_scope_report(
            provider_probes=[{"provider_name": "rancher-prod", "status": "ready", "success": True}],
            sync_dry_run=[{"provider_name": "devtron-prod", "provider_kind": "devtron", "success": True}],
            readonly_rbac_live={
                "success": True,
                "status": "ready",
                "context": "prod-kz",
                "service_account": "system:serviceaccount:webterm-system:webterm-kubernetes-readonly",
            },
        )

    assert report["success"] is True
    assert report["status"] == "ready"
    assert report["core_evidence_ready"] is True
    assert report["missing_reference_count"] == 0
    assert report["local_indicator_count"] == 0


def test_release_scope_requires_core_evidence_refs_for_nonlocal_production():
    with override_settings(KUBERNETES_OPS_RELEASE_ENVIRONMENT="production", KUBERNETES_OPS_PRODUCTION_APPROVAL_REF="CHG-123"):
        report = build_kubernetes_release_scope_report(
            provider_probes=[{"provider_name": "rancher-prod", "status": "ready", "success": True}],
            sync_dry_run=[{"provider_name": "devtron-prod", "provider_kind": "devtron", "success": True}],
            readonly_rbac_live={
                "success": True,
                "status": "ready",
                "context": "prod-kz",
                "service_account": "system:serviceaccount:webterm-system:webterm-kubernetes-readonly",
            },
        )

    assert report["success"] is False
    assert report["status"] == "missing_refs"
    assert report["core_evidence_ready"] is False
    missing_settings = {item["setting"] for item in report["missing_required_references"]}
    assert "KUBERNETES_OPS_PRODUCTION_EVIDENCE_REF" in missing_settings
    assert "KUBERNETES_OPS_KUBERNETES_MCP_EVIDENCE_REF" in missing_settings
    assert "KUBERNETES_OPS_PRODUCTION_ROLLBACK_EVIDENCE_REF" in missing_settings
    assert "KUBERNETES_OPS_PRODUCTION_NATIVE_VERIFICATION_EVIDENCE_REF" in missing_settings


def test_release_scope_blocks_local_kubernetes_mcp_endpoint_for_production():
    with override_settings(KUBERNETES_OPS_RELEASE_ENVIRONMENT="production", KUBERNETES_OPS_PRODUCTION_APPROVAL_REF="CHG-123"):
        report = build_kubernetes_release_scope_report(
            provider_probes=[{"provider_name": "rancher-prod", "status": "ready", "success": True}],
            sync_dry_run=[{"provider_name": "devtron-prod", "provider_kind": "devtron", "success": True}],
            readonly_rbac_live={
                "success": True,
                "status": "ready",
                "context": "prod-kz",
                "service_account": "system:serviceaccount:webterm-system:webterm-kubernetes-readonly",
            },
            studio_mcp={
                "success": True,
                "status": "ready",
                "mcp_server": {"name": "Kubernetes MCP", "transport": "sse", "url": "http://mcp-demo:8765/mcp"},
            },
        )

    assert report["success"] is False
    assert report["status"] == "local_evidence"
    assert any(item["source"] == "studio_mcp.url" for item in report["local_indicators"])
