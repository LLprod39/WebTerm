from __future__ import annotations

from typing import Any

from kubernetes_ops.models import K8sAdminAction, K8sAdminSession, K8sCluster, K8sProvider
from kubernetes_ops.services.admin_node_drain_helpers import (
    _base_response,
    _blocked_reason,
    _eviction_body,
    _eviction_path,
    _has_safe_controller,
    _is_daemonset_pod,
    _is_mirror_pod,
    _is_terminal_pod,
    _list_truncated,
    _pod_identity,
    _pod_node,
    _pods_on_node_path,
    _policy_payload,
    _provider_request,
    _record_action,
    _summary,
    _uses_empty_dir,
)
from kubernetes_ops.services.admin_resources import (
    AdminResourceError,
    KubernetesResourceRef,
    sanitize_kubernetes_resource,
)
from kubernetes_ops.services.admin_write_approval import assert_admin_session_approved
from kubernetes_ops.services.normalizers import payload_items
from kubernetes_ops.services.provider_clients import ProviderJsonClient, ProviderTransport


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
