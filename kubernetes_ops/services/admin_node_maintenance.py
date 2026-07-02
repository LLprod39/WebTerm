from __future__ import annotations

import urllib.parse
from typing import Any

from django.conf import settings
from django.core.exceptions import ValidationError

from kubernetes_ops.models import K8sAdminAction, K8sAdminSession, K8sCluster, K8sProvider
from kubernetes_ops.permissions import kubernetes_permission_policy
from kubernetes_ops.services.admin_resources import (
    AdminResourceError,
    KubernetesResourceRef,
    cluster_for_value,
    rancher_resource_path,
    sanitize_kubernetes_resource,
)
from kubernetes_ops.services.admin_node_drain import execute_node_drain
from kubernetes_ops.services.admin_sessions import refresh_admin_session_state
from kubernetes_ops.services.admin_write_approval import assert_admin_session_approved, assert_production_write_approved
from kubernetes_ops.services.describe import sanitize_metadata
from kubernetes_ops.services.logs import _redact_log_line
from kubernetes_ops.services.provider_clients import KubernetesProviderError, ProviderJsonClient, ProviderTransport

VERB_CORDON = getattr(K8sAdminAction, "VERB_CORDON", "cordon")
VERB_UNCORDON = getattr(K8sAdminAction, "VERB_UNCORDON", "uncordon")
VERB_DRAIN = getattr(K8sAdminAction, "VERB_DRAIN", "drain")
NODE_MAINTENANCE_ACTIONS = {VERB_CORDON, VERB_UNCORDON, VERB_DRAIN}


def run_node_maintenance_action(
    *,
    user,
    session_id: str,
    cluster_id: str,
    action: str,
    node_name: str,
    reason: str,
    confirmation: str = "",
    options: dict[str, Any] | None = None,
    transport: ProviderTransport | None = None,
) -> dict[str, Any]:
    operation = _required_action(action)
    _require_node_maintenance_policy(user)
    node = _required_node_name(node_name)
    reason_value = _required_reason(reason, action=operation)
    option_summary = _option_summary(options or {})
    if operation == VERB_DRAIN:
        _require_drain_confirmation(node=node, confirmation=confirmation)
    cluster = _required_cluster(cluster_id)
    ref = KubernetesResourceRef(api_version="v1", kind="Node", resource="nodes", name=node)
    session = _active_break_glass_node_session(user=user, session_id=session_id, cluster=cluster, ref=ref, verb=operation)
    assert_production_write_approved(session=session, cluster=cluster, ref=ref, action=operation)
    assert_admin_session_approved(session=session, action=operation)
    provider = _required_rancher_provider(cluster)
    path = rancher_resource_path(provider, cluster, ref)
    if operation == VERB_DRAIN:
        if bool(getattr(settings, "KUBERNETES_ADMIN_NODE_DRAIN_EXECUTION_ENABLED", False)):
            return execute_node_drain(
                user=user,
                session=session,
                cluster=cluster,
                provider=provider,
                ref=ref,
                path=path,
                reason=reason_value,
                confirmation=confirmation,
                options=option_summary,
                transport=transport,
            )
        return _blocked_drain_response(
            user=user,
            session=session,
            cluster=cluster,
            provider=provider,
            ref=ref,
            path=path,
            reason=reason_value,
            confirmation=confirmation,
            options=option_summary,
        )
    unschedulable = operation == VERB_CORDON
    patch_body = {"spec": {"unschedulable": unschedulable}}
    try:
        response = _provider_patch(provider, path, patch_body, transport=transport)
    except AdminResourceError as exc:
        _record_node_action(
            user=user,
            session=session,
            cluster=cluster,
            ref=ref,
            verb=operation,
            status=K8sAdminAction.STATUS_FAILED,
            request_payload={"reason": reason_value},
            response_summary={"source": "provider_error", "error": str(exc), "node": node},
        )
        raise
    sanitized_response = sanitize_kubernetes_resource(response)
    action_row = _record_node_action(
        user=user,
        session=session,
        cluster=cluster,
        ref=ref,
        verb=operation,
        status=K8sAdminAction.STATUS_COMPLETED,
        request_payload={"reason": reason_value, "unschedulable": unschedulable},
        response_summary={
            "source": "rancher_kubernetes_node_patch",
            "node": node,
            "unschedulable": unschedulable,
            "server_top_level_fields": sorted(sanitized_response.keys()) if isinstance(sanitized_response, dict) else [],
        },
    )
    return _base_response(
        operation=f"node_{operation}",
        status=K8sAdminAction.STATUS_COMPLETED,
        cluster=cluster,
        provider=provider,
        ref=ref,
        path=path,
        action=action_row,
        extra={
            "node": node,
            "unschedulable": unschedulable,
            "resource": sanitized_response,
            "policy": _policy_payload(mutates_state=True, drain_execution=False),
        },
    )


def _blocked_drain_response(
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
) -> dict[str, Any]:
    blocked_reason = "node_drain_execution_disabled"
    action_row = _record_node_action(
        user=user,
        session=session,
        cluster=cluster,
        ref=ref,
        verb=VERB_DRAIN,
        status=K8sAdminAction.STATUS_EXECUTION_BLOCKED,
        request_payload={"reason": reason, "confirmation": confirmation, "options": options},
        response_summary={
            "source": "webterm_node_drain_guard",
            "blocked_reason": blocked_reason,
            "drain_started": False,
            "evictions_started": False,
            "payload_stored": False,
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
            "blocked_reason": blocked_reason,
            "drain_started": False,
            "evictions_started": False,
            "drain_options": options,
            "policy": _policy_payload(mutates_state=False, drain_execution=False),
        },
    )


def _require_node_maintenance_policy(user) -> None:
    policy = kubernetes_permission_policy(user)
    if not policy.get("can_break_glass"):
        raise AdminResourceError("Kubernetes break-glass access is required.", code="break_glass_required", status=403)
    if not bool(getattr(settings, "KUBERNETES_ADMIN_NATIVE_NODE_MAINTENANCE_ENABLED", False)):
        raise AdminResourceError("Native node maintenance is disabled by policy.", code="native_node_maintenance_disabled", status=403)


def _active_break_glass_node_session(
    *,
    user,
    session_id: str,
    cluster: K8sCluster,
    ref: KubernetesResourceRef,
    verb: str,
) -> K8sAdminSession:
    try:
        session = K8sAdminSession.objects.select_related("user", "provider", "cluster").filter(session_id=session_id, user=user).first()
    except (TypeError, ValueError, ValidationError) as exc:
        raise AdminResourceError("Active break-glass admin session is required.", code="admin_break_glass_session_required", status=403) from exc
    if session is None:
        raise AdminResourceError("Active break-glass admin session is required.", code="admin_break_glass_session_required", status=403)
    session = refresh_admin_session_state(session)
    if session.status != K8sAdminSession.STATUS_ACTIVE:
        raise AdminResourceError("Break-glass admin session is not active.", code="admin_break_glass_session_not_active", status=403)
    if session.mode != K8sAdminSession.MODE_BREAK_GLASS:
        raise AdminResourceError("Node maintenance requires a break-glass admin session.", code="break_glass_session_required", status=403)
    if session.cluster_id and session.cluster_id != cluster.id:
        raise AdminResourceError("Admin session does not cover this cluster.", code="admin_session_cluster_mismatch", status=403)
    if verb not in set(session.allowed_verbs or []):
        raise AdminResourceError("Admin session does not allow this node action.", code="admin_session_verb_denied", status=403)
    allowed_kinds = {str(item).lower() for item in session.allowed_kinds or []}
    if "*" not in allowed_kinds and ref.kind.lower() not in allowed_kinds and "node" not in allowed_kinds:
        raise AdminResourceError("Admin session does not cover node maintenance.", code="admin_session_kind_denied", status=403)
    return session


def _provider_patch(provider: K8sProvider, path: str, body: dict[str, Any], *, transport: ProviderTransport | None) -> dict[str, Any]:
    try:
        return ProviderJsonClient(provider, transport=transport).request(
            "PATCH",
            path,
            body=body,
            extra_headers={"Content-Type": "application/merge-patch+json", "Accept": "application/json"},
        )
    except (KubernetesProviderError, ValueError, KeyError) as exc:
        raise AdminResourceError(str(exc), code="provider_request_failed", status=502) from exc


def _required_action(value: str) -> str:
    operation = str(value or "").strip().lower()
    if operation not in NODE_MAINTENANCE_ACTIONS:
        raise AdminResourceError("node maintenance action must be cordon, uncordon, or drain.", code="node_action_invalid")
    return operation


def _required_node_name(value: str) -> str:
    node = str(value or "").strip()[:253]
    if not node:
        raise AdminResourceError("node_name is required for node maintenance.", code="node_name_required")
    if any(char.isspace() for char in node) or "/" in node or "\\" in node:
        raise AdminResourceError("node_name is invalid.", code="node_name_invalid")
    return node


def _required_reason(value: str, *, action: str) -> str:
    reason = _redact_log_line(str(value or "").replace("\r", "").strip())[:1000]
    if not reason:
        raise AdminResourceError(f"reason is required for node {action}.", code="reason_required")
    return reason


def _require_drain_confirmation(*, node: str, confirmation: str) -> None:
    expected = f"drain Node {node}"
    if str(confirmation or "").strip() != expected:
        raise AdminResourceError("Exact drain confirmation is required.", code="confirmation_required", payload={"expected": expected})


def _option_summary(options: dict[str, Any]) -> dict[str, Any]:
    return sanitize_metadata(
        {
            "ignore_daemonsets": bool(options.get("ignore_daemonsets", True)),
            "delete_emptydir_data": bool(options.get("delete_emptydir_data", False)),
            "force": bool(options.get("force", False)),
            "grace_period_seconds": _bounded_int(options.get("grace_period_seconds"), default=30, minimum=0, maximum=3600),
            "timeout_seconds": _bounded_int(options.get("timeout_seconds"), default=300, minimum=30, maximum=7200),
            "max_pods": _bounded_int(options.get("max_pods"), default=50, minimum=1, maximum=100),
        }
    )


def _bounded_int(value: Any, *, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(parsed, maximum))


def _record_node_action(
    *,
    user,
    session: K8sAdminSession,
    cluster: K8sCluster,
    ref: KubernetesResourceRef,
    verb: str,
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
        verb=verb,
        status=status,
        request_payload_sanitized={"target": _target_payload(ref), **sanitize_metadata(request_payload)},
        response_summary=sanitize_metadata(response_summary),
    )


def _required_cluster(cluster_id: str) -> K8sCluster:
    cluster = cluster_for_value(cluster_id)
    if cluster is None:
        raise AdminResourceError("Cluster not found.", code="cluster_not_found", status=404)
    return cluster


def _required_rancher_provider(cluster: K8sCluster) -> K8sProvider:
    provider = cluster.rancher_provider
    if provider is None or not provider.enabled:
        raise AdminResourceError("Enabled Rancher provider is required for node maintenance.", code="rancher_provider_required", status=409)
    return provider


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
        "cluster": {"id": f"cluster_{cluster.id}", "name": cluster.name, "rancher_cluster_id": cluster.rancher_cluster_id},
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
        "native_node_maintenance_enabled": bool(getattr(settings, "KUBERNETES_ADMIN_NATIVE_NODE_MAINTENANCE_ENABLED", False)),
        "node_drain_execution_enabled": drain_execution and bool(getattr(settings, "KUBERNETES_ADMIN_NODE_DRAIN_EXECUTION_ENABLED", False)),
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


def _public_path(path: str) -> str:
    parsed = urllib.parse.urlsplit(str(path or ""))
    return urllib.parse.urlunsplit(("", "", parsed.path or "/", "", ""))[:500]
