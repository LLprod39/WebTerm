from __future__ import annotations

import json
from typing import Any

from django.contrib.auth import get_user_model
from django.db import transaction

from core_ui.models import UserAppPermission
from kubernetes_ops.models import (
    K8sActionRequest,
    K8sAppRef,
    K8sCluster,
    K8sFleetBundle,
    K8sNetworkRef,
    K8sPodRef,
    K8sProvider,
    K8sWorkloadRef,
)
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
from kubernetes_ops.services.diagnostics_summary import build_diagnostics_summary
from kubernetes_ops.services.helm_ownership import build_helm_ownership_payload
from kubernetes_ops.services.network_detail import build_network_detail
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


def _diagnostics_summary(
    *, user, cluster: K8sCluster, workload: K8sWorkloadRef, network: K8sNetworkRef
) -> dict[str, Any]:
    cluster_payload, cluster_error = build_diagnostics_summary(
        scope="cluster", cluster_id=f"cluster_{cluster.id}", user=user
    )
    workload_payload, workload_error = build_diagnostics_summary(
        scope="workload", workload_id=f"workload_{workload.id}", user=user
    )
    network_payload, network_error = build_diagnostics_summary(
        scope="network", network_id=f"network_{network.id}", user=user
    )
    scopes = {
        "cluster": cluster_payload or {"success": False, "error": cluster_error},
        "workload": workload_payload or {"success": False, "error": workload_error},
        "network": network_payload or {"success": False, "error": network_error},
    }
    return {"success": all(bool(payload.get("success")) for payload in scopes.values()), "scopes": scopes}


def _diagnostics_read_only(payload: dict[str, Any]) -> bool:
    scopes = payload.get("scopes") if isinstance(payload.get("scopes"), dict) else {}
    if not scopes:
        policy = payload.get("policy") if isinstance(payload.get("policy"), dict) else {}
        return policy.get("mutates_state") is False
    for item in scopes.values():
        if not isinstance(item, dict):
            return False
        policy = item.get("policy") if isinstance(item.get("policy"), dict) else {}
        if policy.get("mutates_state") is not False:
            return False
    return True


def _check(check_id: str, success: bool) -> dict[str, Any]:
    return {"id": check_id, "success": bool(success)}


def _all_links_empty(payloads: dict[str, dict[str, Any]]) -> bool:
    return all(not payload.get("links") for key, payload in payloads.items() if key != "provider")


def _all_link_policies(payloads: dict[str, dict[str, Any]], *, visible: bool, mode: str) -> bool:
    for key, payload in payloads.items():
        if key == "provider":
            continue
        policy = payload.get("external_links_policy") if isinstance(payload.get("external_links_policy"), dict) else {}
        if policy.get("visible") is not visible or policy.get("mode") != mode:
            return False
    return True


def _all_nested_links_empty(payload: Any) -> bool:
    if isinstance(payload, dict):
        for key, value in payload.items():
            if key == "links" and value:
                return False
            if not _all_nested_links_empty(value):
                return False
    elif isinstance(payload, list):
        return all(_all_nested_links_empty(item) for item in payload)
    return True


def _all_nested_link_policies(payload: Any, *, visible: bool, mode: str) -> bool:
    if isinstance(payload, dict):
        for key, value in payload.items():
            if key == "external_links_policy":
                policy = value if isinstance(value, dict) else {}
                if policy.get("visible") is not visible or policy.get("mode") != mode:
                    return False
            elif not _all_nested_link_policies(value, visible=visible, mode=mode):
                return False
    elif isinstance(payload, list):
        return all(_all_nested_link_policies(item, visible=visible, mode=mode) for item in payload)
    return True


def _staff_links_visible(payloads: dict[str, dict[str, Any]]) -> bool:
    return all(bool(payload.get("links")) for key, payload in payloads.items() if key != "provider")


def _contains_any(payload: Any, needles: tuple[str, ...]) -> bool:
    text = json.dumps(payload, sort_keys=True)
    unescaped_text = text.replace("\\n", "\n")
    return any(needle in text or needle in unescaped_text for needle in needles)


def _contains_key(payload: Any, key_name: str) -> bool:
    if isinstance(payload, dict):
        return any(str(key) == key_name or _contains_key(value, key_name) for key, value in payload.items())
    if isinstance(payload, list):
        return any(_contains_key(item, key_name) for item in payload)
    return False


def _grant_kubernetes(user) -> None:
    UserAppPermission.objects.update_or_create(user=user, feature="kubernetes", defaults={"allowed": True})


def _user(username: str, *, is_staff: bool):
    User = get_user_model()
    return User.objects.create_user(username=username, password="release-normal-user-proof", is_staff=is_staff)


def _inventory(*, reader):
    provider = K8sProvider.objects.create(
        name="release-normal-user-rancher",
        kind=K8sProvider.KIND_RANCHER,
        base_url="https://release-rancher.example.test",
        auth_mode=K8sProvider.AUTH_SECRET_REF,
        secret_ref="env:RANCHER_TOKEN",
        labels={
            "clusters_path": "/v3/clusters",
            "headers": {"authorization": "Bearer release-provider-token"},
            "support_note": "client-certificate-data: release-provider-ca",
        },
    )
    cluster = K8sCluster.objects.create(
        name="release-normal-user-cluster",
        environment="prod",
        rancher_provider=provider,
        rancher_cluster_id="c-release-normal-user",
        labels={
            "credential": "raw-token",
            "environment": "prod",
            "support_note": "kubeconfig=release-kubeconfig-context",
        },
        links={"rancher": "https://release-rancher.example.test/c/c-release-normal-user?token=raw-token#tail"},
    )
    app = K8sAppRef.objects.create(
        name="release-normal-user-app",
        cluster=cluster,
        namespace="payments",
        owner=K8sAppRef.OWNER_DEVTRON,
        labels={
            "app.kubernetes.io/name": "release-normal-user-app",
            "meta.helm.sh/release-name": "release-normal-user-app",
            "helm.sh/chart": "release-normal-chart",
            "helm_values": {
                "image": {"tag": "release"},
                "password": "raw-token",
                "note": "Bearer release-provider-token",
            },
            "secret": "raw-token",
            "notes": "Bearer release-provider-token",
        },
        links={
            "devtron_app": "https://release-devtron.example.test/app/release-normal-user?token=raw-token#tail",
            "history": "https://release-devtron.example.test/history/release-normal-user?token=raw-token#tail",
            "values": "https://release-devtron.example.test/values/release-normal-user?token=raw-token#tail",
            "logs": "https://release-devtron.example.test/logs/release-normal-user?token=raw-token#tail",
            "rollback": "https://release-devtron.example.test/rollback/release-normal-user?token=raw-token#tail",
            "secret_link": "https://release-devtron.example.test/secret?token=raw-token",
        },
    )
    workload = K8sWorkloadRef.objects.create(
        name="release-normal-user-app",
        cluster=cluster,
        namespace="payments",
        kind=K8sWorkloadRef.KIND_DEPLOYMENT,
        labels={
            "app.kubernetes.io/name": "release-normal-user-app",
            "app.kubernetes.io/managed-by": "Helm",
            "meta.helm.sh/release-name": "release-normal-user-app",
            "password": "raw-token",
            "notes": "token=release-provider-token",
        },
        links={"rancher": "https://release-rancher.example.test/workload/release-normal-user?token=raw-token#tail"},
    )
    pod = K8sPodRef.objects.create(
        cluster=cluster,
        namespace="payments",
        name="release-normal-user-app-abc123",
        labels={
            "app.kubernetes.io/name": "release-normal-user-app",
            "token": "raw-token",
            "notes": "client-key-data: release-provider-key",
        },
        links={"logs": "https://release-rancher.example.test/logs/release-normal-user?token=raw-token#tail"},
    )
    network = K8sNetworkRef.objects.create(
        name="release-normal-user-app",
        cluster=cluster,
        namespace="payments",
        kind=K8sNetworkRef.KIND_SERVICE,
        service_type="ClusterIP",
        ports=[{"port": 80, "targetPort": 8080}],
        endpoints=[
            {
                "pod": "release-normal-user-app-abc123",
                "token": "raw-token",
                "note": "certificate-authority-data: release-provider-ca",
            }
        ],
        labels={"app.kubernetes.io/name": "release-normal-user-app"},
        links={"rancher": "https://release-rancher.example.test/service/release-normal-user?token=raw-token#tail"},
    )
    bundle = K8sFleetBundle.objects.create(
        name="release-normal-user-bundle",
        source="gitrepo/platform",
        target="prod-*",
        labels={"meta.helm.sh/release-name": "release-normal-user-app", "secret": "raw-token"},
        links={"rancher_fleet": "https://release-rancher.example.test/fleet/release-normal-user?token=raw-token#tail"},
    )
    K8sActionRequest.objects.create(
        requested_by=reader,
        username_snapshot=getattr(reader, "username", ""),
        action=K8sActionRequest.ACTION_K8S_RESOURCE_APPLY,
        status=K8sActionRequest.STATUS_EXECUTED_NATIVE,
        risk_tier=K8sActionRequest.RISK_HIGH,
        cluster=cluster,
        target={
            "cluster_id": f"cluster_{cluster.id}",
            "namespace": "payments",
            "kind": "Deployment",
            "name": "release-normal-user-app",
            "token": "raw-token",
            "notes": "Bearer release-provider-token",
        },
        preview={
            "blast_radius": "single_resource",
            "rollback_plan": {
                "status": "required",
                "strategy": "apply_revert",
                "payload_stored": False,
                "sensitive_values_stored": False,
                "evidence": {"password": "raw-token"},
            },
        },
        execution_policy={"native_execution_enabled": True, "credential": "raw-token"},
        report={
            "status": K8sActionRequest.STATUS_EXECUTED_NATIVE,
            "verification_plan": {
                "status": "pending",
                "mode": "native_post_action",
                "required": True,
                "check_ids": ["apply_action_completed", "recent_warning_events_checked"],
                "payload_stored": False,
                "sensitive_values_stored": False,
                "evidence": {"authorization": "Bearer release-provider-token"},
            },
        },
        reason="apply after token=release-provider-token",
        approval_ref="https://release-rancher.example.test/change?token=raw-token#tail",
    )
    return provider, cluster, app, workload, pod, network, bundle
