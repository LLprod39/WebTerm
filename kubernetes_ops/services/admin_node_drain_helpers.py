from __future__ import annotations

import urllib.parse
from typing import Any

from django.conf import settings

from kubernetes_ops.models import K8sAdminAction, K8sAdminSession, K8sCluster, K8sProvider
from kubernetes_ops.services.admin_resources import (
    AdminResourceError,
    KubernetesResourceRef,
    rancher_api_path,
)
from kubernetes_ops.services.describe import sanitize_metadata
from kubernetes_ops.services.provider_clients import KubernetesProviderError, ProviderJsonClient


def _blocked_reason(blockers: dict[str, int]) -> str:
    if blockers["pod_list_truncated"]:
        return "drain_pod_list_truncated"
    if blockers["daemonset"]:
        return "daemonsets_require_ignore"
    if blockers["emptydir"]:
        return "emptydir_data_confirmation_required"
    if blockers["unmanaged"]:
        return "unmanaged_pods_require_force"
    if blockers["pod_limit"]:
        return "drain_pod_limit_exceeded"
    return ""


def _pod_identity(pod: dict[str, Any]) -> tuple[str, str]:
    metadata = pod.get("metadata") if isinstance(pod, dict) else {}
    if not isinstance(metadata, dict):
        return "", ""
    return str(metadata.get("namespace") or ""), str(metadata.get("name") or "")


def _pod_node(pod: dict[str, Any]) -> str:
    spec = pod.get("spec") if isinstance(pod, dict) else {}
    return str(spec.get("nodeName") or "") if isinstance(spec, dict) else ""


def _is_terminal_pod(pod: dict[str, Any]) -> bool:
    status = pod.get("status") if isinstance(pod, dict) else {}
    return str(status.get("phase") or "").lower() in {"succeeded", "failed"} if isinstance(status, dict) else False


def _is_mirror_pod(pod: dict[str, Any]) -> bool:
    metadata = pod.get("metadata") if isinstance(pod, dict) else {}
    annotations = metadata.get("annotations") if isinstance(metadata, dict) else {}
    return isinstance(annotations, dict) and bool(annotations.get("kubernetes.io/config.mirror"))


def _is_daemonset_pod(pod: dict[str, Any]) -> bool:
    return "DaemonSet" in _owner_kinds(pod)


def _has_safe_controller(pod: dict[str, Any]) -> bool:
    return bool(_owner_kinds(pod) & {"ReplicaSet", "ReplicationController", "StatefulSet", "Job"})


def _owner_kinds(pod: dict[str, Any]) -> set[str]:
    metadata = pod.get("metadata") if isinstance(pod, dict) else {}
    refs = metadata.get("ownerReferences") if isinstance(metadata, dict) else []
    if not isinstance(refs, list):
        refs = []
    return {str(ref.get("kind") or "") for ref in refs if isinstance(ref, dict)}


def _uses_empty_dir(pod: dict[str, Any]) -> bool:
    spec = pod.get("spec") if isinstance(pod, dict) else {}
    volumes = spec.get("volumes") if isinstance(spec, dict) else []
    if not isinstance(volumes, list):
        volumes = []
    return any(isinstance(volume, dict) and "emptyDir" in volume for volume in volumes)


def _list_truncated(payload: dict[str, Any]) -> bool:
    metadata = payload.get("metadata") if isinstance(payload, dict) else {}
    return bool(metadata.get("continue") if isinstance(metadata, dict) else payload.get("continue"))


def _pods_on_node_path(provider: K8sProvider, cluster: K8sCluster, *, node: str, limit: int) -> str:
    query = urllib.parse.urlencode({"fieldSelector": f"spec.nodeName={node}", "limit": str(limit + 1)})
    return f"{rancher_api_path(provider, cluster, 'v1')}/pods?{query}"


def _eviction_path(provider: K8sProvider, cluster: K8sCluster, *, namespace: str, name: str) -> str:
    base = rancher_api_path(provider, cluster, "v1")
    return f"{base}/namespaces/{_quote(namespace)}/pods/{_quote(name)}/eviction"


def _eviction_body(pod: dict[str, str], options: dict[str, Any]) -> dict[str, Any]:
    return {
        "apiVersion": "policy/v1",
        "kind": "Eviction",
        "metadata": {"name": pod["name"], "namespace": pod["namespace"]},
        "deleteOptions": {"gracePeriodSeconds": int(options.get("grace_period_seconds") or 30)},
    }


def _provider_request(
    client: ProviderJsonClient,
    method: str,
    path: str,
    *,
    body: dict[str, Any] | None = None,
    extra_headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    try:
        return client.request(method, path, body=body, extra_headers=extra_headers)
    except (KubernetesProviderError, ValueError, KeyError) as exc:
        raise AdminResourceError(str(exc), code="provider_request_failed", status=502) from exc


def _record_action(
    *,
    user,
    session: K8sAdminSession,
    cluster: K8sCluster,
    ref: KubernetesResourceRef,
    status: str,
    request_payload: dict[str, Any],
    response_summary: dict[str, Any],
) -> K8sAdminAction:
    return K8sAdminAction.objects.create(
        session=session,
        user=user,
        username_snapshot=getattr(user, "username", ""),
        cluster=cluster,
        namespace="",
        resource_api_version=ref.api_version,
        resource_kind=ref.kind,
        resource_name=ref.name,
        verb=K8sAdminAction.VERB_DRAIN,
        status=status,
        request_payload_sanitized={"target": _target_payload(ref), **sanitize_metadata(request_payload)},
        response_summary=sanitize_metadata(response_summary),
    )


def _summary(plan: dict[str, Any]) -> dict[str, Any]:
    blockers = {key: value for key, value in plan["blockers"].items() if value}
    return {
        "pods_considered": plan["pods_considered"],
        "evictable_pod_count": len(plan["evictable_pods"]),
        "pods_skipped": plan["pods_skipped"],
        "blockers": blockers,
    }


def _base_response(
    *,
    operation: str,
    status: str,
    cluster: K8sCluster,
    provider: K8sProvider,
    ref: KubernetesResourceRef,
    path: str,
    action: K8sAdminAction,
    extra: dict[str, Any],
) -> dict[str, Any]:
    return {
        "success": True,
        "mode": "admin_break_glass_node_maintenance",
        "operation": operation,
        "status": status,
        "cluster": {
            "id": f"cluster_{cluster.id}",
            "name": cluster.name,
            "rancher_cluster_id": cluster.rancher_cluster_id,
        },
        "provider": {"id": provider.id, "name": provider.name, "kind": provider.kind},
        "target": _target_payload(ref),
        "path": _public_path(path),
        "action": {"id": str(action.action_id), "status": action.status},
        **extra,
    }


def _policy_payload(*, mutates_state: bool, drain_execution: bool) -> dict[str, Any]:
    return {
        "mutates_state": mutates_state,
        "requires_active_admin_session": True,
        "requires_break_glass_session": True,
        "requires_approval": True,
        "requires_node_scope": True,
        "uses_eviction_api": True,
        "native_node_maintenance_enabled": bool(
            getattr(settings, "KUBERNETES_ADMIN_NATIVE_NODE_MAINTENANCE_ENABLED", False)
        ),
        "node_drain_execution_enabled": drain_execution
        and bool(getattr(settings, "KUBERNETES_ADMIN_NODE_DRAIN_EXECUTION_ENABLED", False)),
        "blocked_actions": ["exec", "port_forward", "node_debug", "cluster_terminal"],
    }


def _target_payload(ref: KubernetesResourceRef) -> dict[str, Any]:
    return {
        "api_version": ref.api_version,
        "kind": ref.kind,
        "resource": ref.resource,
        "namespace": ref.namespace,
        "name": ref.name,
    }


def _quote(value: str) -> str:
    return urllib.parse.quote(str(value), safe="")


def _public_path(path: str) -> str:
    parsed = urllib.parse.urlsplit(str(path or ""))
    return urllib.parse.urlunsplit(("", "", parsed.path or "/", "", ""))[:500]
