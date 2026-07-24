from __future__ import annotations

from typing import Any

from django.db import transaction

from kubernetes_ops.permissions import kubernetes_permission_policy
from kubernetes_ops.serializers import (
    serialize_app,
    serialize_cluster,
    serialize_fleet_bundle,
    serialize_network_ref,
    serialize_pod_ref,
    serialize_provider,
    serialize_workload,
)
from kubernetes_ops.services.action_summary import build_action_request_summary
from kubernetes_ops.services.capabilities import build_kubernetes_capabilities_payload
from kubernetes_ops.services.devtron_app_detail import build_devtron_app_detail
from kubernetes_ops.services.helm_ownership import build_helm_ownership_payload
from kubernetes_ops.services.network_detail import build_network_detail
from kubernetes_ops.services.release_normal_user_surface_helpers import (
    _all_link_policies,
    _all_links_empty,
    _all_nested_link_policies,
    _all_nested_links_empty,
    _check,
    _contains_any,
    _contains_key,
    _diagnostics_read_only,
    _diagnostics_summary,
    _grant_kubernetes,
    _inventory,
    _staff_links_visible,
    _user,
)
from kubernetes_ops.services.release_readiness_summary import build_kubernetes_release_readiness_summary

FRONTEND_CREDENTIAL_MARKERS = (
    "env:RANCHER_TOKEN",
    "env:DEVTRON_TOKEN",
    "vault://release/provider",
    "Bearer release-provider-token",
    "token=release-provider-token",
    "client-certificate-data:",
    "client-key-data:",
    "certificate-authority-data:",
    "release-kubeconfig-context",
)


def build_kubernetes_release_normal_user_surface_evidence(enabled: bool) -> dict[str, Any]:
    if not enabled:
        return {"success": False, "status": "skipped", "reason": "normal-user WebTerm-only surface proof skipped"}
    try:
        with transaction.atomic():
            reader = _user("release-k8s-normal-reader", is_staff=False)
            staff = _user("release-k8s-fallback-staff", is_staff=True)
            _grant_kubernetes(reader)
            _grant_kubernetes(staff)
            provider, cluster, app, workload, pod, network, bundle = _inventory(reader=reader)
            proof = _run_surface_checks(
                reader=reader,
                staff=staff,
                provider=provider,
                cluster=cluster,
                app=app,
                workload=workload,
                pod=pod,
                network=network,
                bundle=bundle,
            )
            transaction.set_rollback(True)
            return proof
    except Exception as exc:
        return {"success": False, "status": "error", "error": str(exc)}


def _run_surface_checks(*, reader, staff, provider, cluster, app, workload, pod, network, bundle) -> dict[str, Any]:
    reader_policy = kubernetes_permission_policy(reader)
    staff_policy = kubernetes_permission_policy(staff)
    reader_payloads = {
        "provider": serialize_provider(provider, user=reader),
        "cluster": serialize_cluster(cluster, user=reader),
        "app": serialize_app(app, user=reader),
        "workload": serialize_workload(workload, user=reader),
        "pod": serialize_pod_ref(pod, user=reader),
        "network": serialize_network_ref(network, user=reader),
        "fleet_bundle": serialize_fleet_bundle(bundle, user=reader),
    }
    staff_payloads = {
        "provider": serialize_provider(provider, user=staff),
        "cluster": serialize_cluster(cluster, user=staff),
        "app": serialize_app(app, user=staff),
        "workload": serialize_workload(workload, user=staff),
        "pod": serialize_pod_ref(pod, user=staff),
        "network": serialize_network_ref(network, user=staff),
        "fleet_bundle": serialize_fleet_bundle(bundle, user=staff),
    }
    reader_network_detail = build_network_detail(network, user=reader)
    staff_network_detail = build_network_detail(network, user=staff)
    reader_helm_releases = build_helm_ownership_payload(user=reader)
    staff_helm_releases = build_helm_ownership_payload(user=staff)
    reader_devtron_detail = build_devtron_app_detail(app, user=reader)
    staff_devtron_detail = build_devtron_app_detail(app, user=staff)
    reader_diagnostics_summary = _diagnostics_summary(user=reader, cluster=cluster, workload=workload, network=network)
    staff_diagnostics_summary = _diagnostics_summary(user=staff, cluster=cluster, workload=workload, network=network)
    reader_action_summary = build_action_request_summary(user=reader)
    staff_action_summary = build_action_request_summary(user=staff, include_all=True)
    reader_capabilities = build_kubernetes_capabilities_payload(reader)
    staff_capabilities = build_kubernetes_capabilities_payload(staff)
    staff_release_summary = build_kubernetes_release_readiness_summary(user=staff)
    reader_frontend_surface = {
        "payloads": reader_payloads,
        "network_detail": reader_network_detail,
        "helm_releases": reader_helm_releases,
        "devtron_app_detail": reader_devtron_detail,
        "diagnostics_summary": reader_diagnostics_summary,
        "action_summary": reader_action_summary,
        "capabilities": reader_capabilities,
    }
    staff_frontend_surface = {
        "payloads": staff_payloads,
        "network_detail": staff_network_detail,
        "helm_releases": staff_helm_releases,
        "devtron_app_detail": staff_devtron_detail,
        "diagnostics_summary": staff_diagnostics_summary,
        "action_summary": staff_action_summary,
        "capabilities": staff_capabilities,
        "release_summary": staff_release_summary,
    }
    checks = [
        _check("reader_can_read", reader_policy.get("can_read") is True),
        _check("reader_cannot_audit_deeplinks", reader_policy.get("can_audit_deeplinks") is False),
        _check("reader_provider_base_url_hidden", reader_payloads["provider"].get("base_url") == ""),
        _check(
            "reader_provider_connection_hidden", reader_payloads["provider"].get("connection_details_visible") is False
        ),
        _check("reader_provider_secret_reference_hidden", not _contains_key(reader_payloads["provider"], "secret_ref")),
        _check("reader_external_links_hidden", _all_links_empty(reader_payloads)),
        _check(
            "reader_link_policy_webterm_only",
            _all_link_policies(reader_payloads, visible=False, mode="webterm_native_only"),
        ),
        _check(
            "reader_payload_has_no_external_hosts_or_tokens",
            not _contains_any(
                reader_payloads, ("release-rancher.example.test", "release-devtron.example.test", "raw-token")
            ),
        ),
        _check("reader_network_detail_external_links_hidden", _all_nested_links_empty(reader_network_detail)),
        _check(
            "reader_network_detail_link_policy_webterm_only",
            _all_nested_link_policies(reader_network_detail, visible=False, mode="webterm_native_only"),
        ),
        _check(
            "reader_network_detail_has_no_external_hosts_or_tokens",
            not _contains_any(
                reader_network_detail, ("release-rancher.example.test", "release-devtron.example.test", "raw-token")
            ),
        ),
        _check("reader_helm_releases_external_links_hidden", _all_nested_links_empty(reader_helm_releases)),
        _check(
            "reader_helm_releases_has_no_external_hosts_or_tokens",
            not _contains_any(
                reader_helm_releases, ("release-rancher.example.test", "release-devtron.example.test", "raw-token")
            ),
        ),
        _check("reader_devtron_detail_external_links_hidden", _all_nested_links_empty(reader_devtron_detail)),
        _check(
            "reader_devtron_detail_has_no_external_hosts_or_tokens",
            not _contains_any(
                reader_devtron_detail, ("release-rancher.example.test", "release-devtron.example.test", "raw-token")
            ),
        ),
        _check("reader_diagnostics_summary_read_only", _diagnostics_read_only(reader_diagnostics_summary)),
        _check(
            "reader_diagnostics_summary_has_no_external_hosts_or_tokens",
            not _contains_any(
                reader_diagnostics_summary,
                ("release-rancher.example.test", "release-devtron.example.test", "raw-token"),
            ),
        ),
        _check(
            "reader_action_summary_read_only", (reader_action_summary.get("policy") or {}).get("mutates_state") is False
        ),
        _check(
            "reader_action_summary_has_no_external_hosts_or_tokens",
            not _contains_any(
                reader_action_summary, ("release-rancher.example.test", "release-devtron.example.test", "raw-token")
            ),
        ),
        _check(
            "reader_capabilities_read_only", (reader_capabilities.get("policy") or {}).get("mutates_state") is False
        ),
        _check(
            "reader_capabilities_has_no_external_hosts_or_tokens",
            not _contains_any(
                reader_capabilities, ("release-rancher.example.test", "release-devtron.example.test", "raw-token")
            ),
        ),
        _check(
            "reader_frontend_response_credentials_absent",
            not _contains_any(reader_frontend_surface, FRONTEND_CREDENTIAL_MARKERS),
        ),
        _check("staff_can_audit_deeplinks", staff_policy.get("can_audit_deeplinks") is True),
        _check(
            "staff_provider_connection_visible", staff_payloads["provider"].get("connection_details_visible") is True
        ),
        _check("staff_provider_secret_reference_hidden", not _contains_key(staff_payloads["provider"], "secret_ref")),
        _check("staff_external_links_visible", _staff_links_visible(staff_payloads)),
        _check(
            "staff_external_links_sanitized",
            not _contains_any(staff_payloads, ("raw-token", "?token=", "#tail", "user:pass@")),
        ),
        _check(
            "staff_network_detail_fallback_links_visible",
            bool(staff_network_detail.get("network_ref", {}).get("links", {}).get("rancher")),
        ),
        _check(
            "staff_network_detail_fallback_links_sanitized",
            not _contains_any(staff_network_detail, ("raw-token", "?token=", "#tail", "user:pass@")),
        ),
        _check(
            "staff_helm_releases_fallback_links_sanitized",
            not _contains_any(staff_helm_releases, ("raw-token", "?token=", "#tail", "user:pass@")),
        ),
        _check(
            "staff_devtron_detail_fallback_links_sanitized",
            not _contains_any(staff_devtron_detail, ("raw-token", "?token=", "#tail", "user:pass@")),
        ),
        _check("staff_diagnostics_summary_read_only", _diagnostics_read_only(staff_diagnostics_summary)),
        _check(
            "staff_diagnostics_summary_has_no_external_hosts_or_tokens",
            not _contains_any(
                staff_diagnostics_summary, ("release-rancher.example.test", "release-devtron.example.test", "raw-token")
            ),
        ),
        _check(
            "staff_action_summary_read_only", (staff_action_summary.get("policy") or {}).get("mutates_state") is False
        ),
        _check(
            "staff_action_summary_has_no_external_hosts_or_tokens",
            not _contains_any(
                staff_action_summary, ("release-rancher.example.test", "release-devtron.example.test", "raw-token")
            ),
        ),
        _check("staff_capabilities_read_only", (staff_capabilities.get("policy") or {}).get("mutates_state") is False),
        _check(
            "staff_capabilities_has_no_external_hosts_or_tokens",
            not _contains_any(
                staff_capabilities, ("release-rancher.example.test", "release-devtron.example.test", "raw-token")
            ),
        ),
        _check(
            "staff_release_summary_read_only", (staff_release_summary.get("policy") or {}).get("mutates_state") is False
        ),
        _check(
            "staff_release_summary_has_no_external_hosts_or_tokens",
            not _contains_any(
                staff_release_summary, ("release-rancher.example.test", "release-devtron.example.test", "raw-token")
            ),
        ),
        _check(
            "staff_sensitive_link_key_redacted",
            staff_payloads["app"].get("links", {}).get("secret_link") == "[redacted]",
        ),
        _check(
            "staff_frontend_response_credentials_absent",
            not _contains_any(staff_frontend_surface, FRONTEND_CREDENTIAL_MARKERS),
        ),
    ]
    success = all(item["success"] for item in checks)
    credential_scan_ready = all(
        item["success"]
        for item in checks
        if item["id"]
        in {
            "reader_provider_secret_reference_hidden",
            "reader_frontend_response_credentials_absent",
            "staff_provider_secret_reference_hidden",
            "staff_frontend_response_credentials_absent",
        }
    )
    return {
        "success": success,
        "status": "ready" if success else "failed",
        "mode": "transaction_rollback",
        "checks": checks,
        "checked_count": len(checks),
        "reader": {
            "can_read": bool(reader_policy.get("can_read")),
            "can_audit_deeplinks": bool(reader_policy.get("can_audit_deeplinks")),
        },
        "staff": {
            "can_read": bool(staff_policy.get("can_read")),
            "can_audit_deeplinks": bool(staff_policy.get("can_audit_deeplinks")),
        },
        "reader_external_link_policy": reader_payloads["cluster"].get("external_links_policy", {}),
        "staff_external_link_policy": staff_payloads["cluster"].get("external_links_policy", {}),
        "frontend_response_credential_scan": {
            "status": "ready" if credential_scan_ready else "failed",
            "surfaces_checked": len(reader_payloads) + len(staff_payloads) + 17,
            "provider_secret_reference_serialized": _contains_key(reader_payloads["provider"], "secret_ref")
            or _contains_key(staff_payloads["provider"], "secret_ref"),
            "forbidden_values_found": _contains_any(reader_frontend_surface, FRONTEND_CREDENTIAL_MARKERS)
            or _contains_any(staff_frontend_surface, FRONTEND_CREDENTIAL_MARKERS),
        },
        "persistent_rows": False,
    }
