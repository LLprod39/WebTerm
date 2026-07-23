from __future__ import annotations

import urllib.parse
from typing import Any

from django.conf import settings

from kubernetes_ops.models import K8sAdminAction, K8sAdminSession, K8sCluster, K8sProvider
from kubernetes_ops.services.admin_resources import (
    AdminResourceError,
    KubernetesResourceRef,
    rancher_api_path,
    sanitize_kubernetes_resource,
)
from kubernetes_ops.services.admin_write_approval import assert_admin_session_approved
from kubernetes_ops.services.describe import sanitize_metadata
from kubernetes_ops.services.normalizers import payload_items
from kubernetes_ops.services.provider_clients import KubernetesProviderError, ProviderJsonClient, ProviderTransport


def execute_node_drain(
    *,
    user,
    session: K8sAdminSession,
    cluster: K8sCluster,
    provider: K8sProvider,
    ref: KubernetesResourceRef,
    path: str,
    reason: str,
    confirmation: str,
    options: dict[str, Any],
    transport: ProviderTransport | None = None,
) -> dict[str, Any]:
    client = ProviderJsonClient(provider, transport=transport)
    pods_path = _pods_on_node_path(provider, cluster, node=ref.name, limit=int(options.get("max_pods") or 50))
    try:
        pods_payload = _provider_request(client, "GET", pods_path)
    except AdminResourceError as exc:
        _record_action(
            user=user,
            session=session,
            cluster=cluster,
            ref=ref,
            status=K8sAdminAction.STATUS_FAILED,
            request_payload={"reason": reason, "confirmation": confirmation, "options": options},
            response_summary={"source": "provider_node_drain_preflight", "error": str(exc), "pods_considered": 0},
        )
        raise
    pods = payload_items(pods_payload)
    plan = _drain_plan(pods, node=ref.name, options=options, list_truncated=_list_truncated(pods_payload))
    if plan["blocked_reason"]:
        return _blocked_response(
            user=user,
            session=session,
            cluster=cluster,
            provider=provider,
            ref=ref,
            path=path,
            reason=reason,
            confirmation=confirmation,
            options=options,
            plan=plan,
        )
    try:
        node_response = _provider_request(
            client,
            "PATCH",
            path,
            body={"spec": {"unschedulable": True}},
            extra_headers={"Content-Type": "application/merge-patch+json", "Accept": "application/json"},
        )
        evictions = []
        for pod in plan["evictable_pods"]:
            eviction_path = _eviction_path(provider, cluster, namespace=pod["namespace"], name=pod["name"])
            _provider_request(client, "POST", eviction_path, body=_eviction_body(pod, options))
            evictions.append({"namespace": pod["namespace"], "name": pod["name"], "status": "eviction_requested"})
    except AdminResourceError as exc:
        _record_action(
            user=user,
            session=session,
            cluster=cluster,
            ref=ref,
            status=K8sAdminAction.STATUS_FAILED,
            request_payload={"reason": reason, "confirmation": confirmation, "options": options},
            response_summary={"source": "provider_node_drain", "error": str(exc), **_summary(plan)},
        )
        raise
    sanitized_node = sanitize_kubernetes_resource(node_response)
    action_row = _record_action(
        user=user,
        session=session,
        cluster=cluster,
        ref=ref,
        status=K8sAdminAction.STATUS_COMPLETED,
        request_payload={"reason": reason, "confirmation": confirmation, "options": options},
        response_summary={
            "source": "rancher_kubernetes_eviction_api",
            "cordoned": True,
            "evictions_requested": len(evictions),
            "payload_stored": False,
            **_summary(plan),
        },
    )
    return _base_response(
        operation="node_drain",
        status=K8sAdminAction.STATUS_COMPLETED,
        cluster=cluster,
        provider=provider,
        ref=ref,
        path=path,
        action=action_row,
        extra={
            "node": ref.name,
            "drain_started": True,
            "cordoned": True,
            "evictions_started": bool(evictions),
            "evictions_requested": len(evictions),
            "evictions": evictions,
            "pods_considered": plan["pods_considered"],
            "pods_skipped": plan["pods_skipped"],
            "drain_options": options,
            "resource": sanitized_node,
            "policy": _policy_payload(mutates_state=True, drain_execution=True),
        },
    )


def build_node_drain_preflight(
    *,
    user,
    session: K8sAdminSession,
    cluster: K8sCluster,
    provider: K8sProvider,
    ref: KubernetesResourceRef,
    path: str,
    reason: str,
    confirmation: str,
    options: dict[str, Any],
    transport: ProviderTransport | None = None,
) -> dict[str, Any]:
    if session.status != K8sAdminSession.STATUS_ACTIVE or session.mode != K8sAdminSession.MODE_BREAK_GLASS:
        raise AdminResourceError(
            "Active approved break-glass session is required for node drain preflight.",
            code="admin_break_glass_session_required",
            status=403,
        )
    assert_admin_session_approved(session=session, action=K8sAdminAction.VERB_DRAIN)
    client = ProviderJsonClient(provider, transport=transport)
    pods_path = _pods_on_node_path(provider, cluster, node=ref.name, limit=int(options.get("max_pods") or 50))
    try:
        pods_payload = _provider_request(client, "GET", pods_path)
    except AdminResourceError as exc:
        _record_action(
            user=user,
            session=session,
            cluster=cluster,
            ref=ref,
            status=K8sAdminAction.STATUS_FAILED,
            request_payload={
                "reason": reason,
                "confirmation": confirmation,
                "options": options,
                "preflight_only": True,
            },
            response_summary={"source": "provider_node_drain_preflight", "error": str(exc), "pods_considered": 0},
        )
        raise
    plan = _drain_plan(
        payload_items(pods_payload), node=ref.name, options=options, list_truncated=_list_truncated(pods_payload)
    )
    action_row = _record_action(
        user=user,
        session=session,
        cluster=cluster,
        ref=ref,
        status=K8sAdminAction.STATUS_PLANNED,
        request_payload={"reason": reason, "confirmation": confirmation, "options": options, "preflight_only": True},
        response_summary={
            "source": "provider_node_drain_preflight",
            "drain_started": False,
            "evictions_started": False,
            "payload_stored": False,
            **_summary(plan),
        },
    )
    return _base_response(
        operation="node_drain_preflight",
        status=K8sAdminAction.STATUS_PLANNED,
        cluster=cluster,
        provider=provider,
        ref=ref,
        path=path,
        action=action_row,
        extra={
            "node": ref.name,
            "blocked_reason": plan["blocked_reason"],
            "drain_started": False,
            "evictions_started": False,
            "pods_considered": plan["pods_considered"],
            "evictable_pod_count": len(plan["evictable_pods"]),
            "pods_skipped": plan["pods_skipped"],
            "drain_options": options,
            "policy": _policy_payload(mutates_state=False, drain_execution=False),
        },
    )


def _blocked_response(
    *,
    user,
    session: K8sAdminSession,
    cluster: K8sCluster,
    provider: K8sProvider,
    ref: KubernetesResourceRef,
    path: str,
    reason: str,
    confirmation: str,
    options: dict[str, Any],
    plan: dict[str, Any],
) -> dict[str, Any]:
    action_row = _record_action(
        user=user,
        session=session,
        cluster=cluster,
        ref=ref,
        status=K8sAdminAction.STATUS_EXECUTION_BLOCKED,
        request_payload={"reason": reason, "confirmation": confirmation, "options": options},
        response_summary={
            "source": "webterm_node_drain_preflight",
            "blocked_reason": plan["blocked_reason"],
            "drain_started": False,
            "evictions_started": False,
            "payload_stored": False,
            **_summary(plan),
        },
    )
    return _base_response(
        operation="node_drain",
        status=K8sAdminAction.STATUS_EXECUTION_BLOCKED,
        cluster=cluster,
        provider=provider,
        ref=ref,
        path=path,
        action=action_row,
        extra={
            "node": ref.name,
            "blocked_reason": plan["blocked_reason"],
            "drain_started": False,
            "evictions_started": False,
            "pods_considered": plan["pods_considered"],
            "pods_skipped": plan["pods_skipped"],
            "drain_options": options,
            "policy": _policy_payload(mutates_state=False, drain_execution=True),
        },
    )


def _drain_plan(
    pods: list[dict[str, Any]], *, node: str, options: dict[str, Any], list_truncated: bool = False
) -> dict[str, Any]:
    evictable: list[dict[str, str]] = []
    skipped = {"daemonset": 0, "mirror": 0, "terminal": 0, "other_node": 0}
    blockers = {
        "daemonset": 0,
        "emptydir": 0,
        "unmanaged": 0,
        "pod_limit": 0,
        "pod_list_truncated": int(list_truncated),
    }
    for pod in pods:
        namespace, name = _pod_identity(pod)
        if not name or _pod_node(pod) != node:
            skipped["other_node"] += 1
            continue
        if _is_terminal_pod(pod):
            skipped["terminal"] += 1
            continue
        if _is_mirror_pod(pod):
            skipped["mirror"] += 1
            continue
        if _is_daemonset_pod(pod):
            if options.get("ignore_daemonsets", True):
                skipped["daemonset"] += 1
            else:
                blockers["daemonset"] += 1
            continue
        if _uses_empty_dir(pod) and not options.get("delete_emptydir_data", False):
            blockers["emptydir"] += 1
            continue
        if not _has_safe_controller(pod) and not options.get("force", False):
            blockers["unmanaged"] += 1
            continue
        evictable.append({"namespace": namespace or "default", "name": name})
    max_pods = int(options.get("max_pods") or 50)
    if len(evictable) > max_pods:
        blockers["pod_limit"] = len(evictable)
        evictable = []
    return {
        "pods_considered": len(pods),
        "evictable_pods": evictable,
        "pods_skipped": skipped,
        "blockers": blockers,
        "blocked_reason": _blocked_reason(blockers),
    }


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
