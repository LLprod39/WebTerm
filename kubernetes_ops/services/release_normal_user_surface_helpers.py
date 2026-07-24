from __future__ import annotations

import json
from typing import Any

from django.contrib.auth import get_user_model

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
from kubernetes_ops.services.diagnostics_summary import build_diagnostics_summary


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
