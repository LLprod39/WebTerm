from __future__ import annotations

import urllib.parse
from typing import Any

from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils import timezone

from kubernetes_ops.models import K8sAdminAction, K8sAdminSession, K8sCluster, K8sProvider
from kubernetes_ops.permissions import kubernetes_permission_policy
from kubernetes_ops.services.admin_owner_guard import assert_direct_admin_mutation_allowed
from kubernetes_ops.services.admin_ownership import build_admin_resource_ownership
from kubernetes_ops.services.admin_resources import (
    AdminResourceError,
    KubernetesResourceRef,
    build_resource_ref,
    cluster_for_value,
    rancher_resource_path,
    sanitize_kubernetes_resource,
)
from kubernetes_ops.services.admin_sessions import refresh_admin_session_state
from kubernetes_ops.services.admin_write_approval import assert_admin_session_approved, assert_production_write_approved
from kubernetes_ops.services.describe import sanitize_metadata
from kubernetes_ops.services.provider_clients import KubernetesProviderError, ProviderJsonClient, ProviderTransport

SCALABLE_KINDS = {"Deployment", "StatefulSet", "ReplicaSet"}
RESTARTABLE_KINDS = {"Deployment", "StatefulSet", "DaemonSet"}


def scale_kubernetes_workload(
    *,
    user,
    session_id: str,
    cluster_id: str,
    api_version: str,
    kind: str,
    namespace: str,
    name: str,
    replicas: Any,
    reason: str,
    resource: str = "",
    transport: ProviderTransport | None = None,
) -> dict[str, Any]:
    if not bool(getattr(settings, "KUBERNETES_ADMIN_NATIVE_SCALE_ENABLED", False)):
        raise AdminResourceError("Native Kubernetes scale is disabled by policy.", code="native_scale_disabled", status=403)
    ref = build_resource_ref(api_version=api_version, kind=kind, namespace=namespace, name=name, resource=resource)
    if ref.kind not in SCALABLE_KINDS:
        raise AdminResourceError("This kind cannot be scaled by Admin Mode.", code="kind_not_scalable")
    replicas_value = _clean_replicas(replicas)
    reason_value = _required_reason(reason, action="scale")
    cluster = _required_cluster(cluster_id)
    session = _active_workload_session_for_user(user, session_id, cluster, ref=ref, verb=K8sAdminAction.VERB_SCALE, policy_key="can_scale")
    assert_production_write_approved(session=session, cluster=cluster, ref=ref, action="scale")
    assert_admin_session_approved(session=session, action=K8sAdminAction.VERB_SCALE)
    provider = _required_rancher_provider(cluster)
    path = f"{rancher_resource_path(provider, cluster, ref)}/scale"
    assert_direct_admin_mutation_allowed(cluster=cluster, ref=ref, action="scale")
    patch = {"spec": {"replicas": replicas_value}}
    try:
        response = _provider_patch(provider, path, patch, transport=transport)
    except AdminResourceError as exc:
        _record_workload_action(
            user=user,
            session=session,
            cluster=cluster,
            ref=ref,
            verb=K8sAdminAction.VERB_SCALE,
            status=K8sAdminAction.STATUS_FAILED,
            request_payload={"reason": reason_value, "replicas": replicas_value},
            response_summary={"source": "provider_error", "error": str(exc)},
        )
        raise
    sanitized_response = sanitize_kubernetes_resource(response)
    ownership = build_admin_resource_ownership(cluster=cluster, ref=ref, resource=sanitized_response)
    action = _record_workload_action(
        user=user,
        session=session,
        cluster=cluster,
        ref=ref,
        verb=K8sAdminAction.VERB_SCALE,
        status=K8sAdminAction.STATUS_COMPLETED,
        request_payload={"reason": reason_value, "replicas": replicas_value},
        response_summary={
            "source": "rancher_kubernetes_scale",
            "replicas": replicas_value,
            "ownership_owner": ownership.get("owner"),
            "server_top_level_fields": sorted(sanitized_response.keys()),
        },
    )
    return _base_response(
        "scale",
        cluster,
        provider,
        ref,
        path,
        action,
        {
            "replicas": replicas_value,
            "resource": sanitized_response,
            "ownership": ownership,
        },
    )


def restart_kubernetes_workload(
    *,
    user,
    session_id: str,
    cluster_id: str,
    api_version: str,
    kind: str,
    namespace: str,
    name: str,
    reason: str,
    resource: str = "",
    transport: ProviderTransport | None = None,
) -> dict[str, Any]:
    if not bool(getattr(settings, "KUBERNETES_ADMIN_NATIVE_RESTART_ENABLED", False)):
        raise AdminResourceError("Native Kubernetes restart is disabled by policy.", code="native_restart_disabled", status=403)
    ref = build_resource_ref(api_version=api_version, kind=kind, namespace=namespace, name=name, resource=resource)
    if ref.kind not in RESTARTABLE_KINDS:
        raise AdminResourceError("This kind cannot be restarted by Admin Mode.", code="kind_not_restartable")
    reason_value = _required_reason(reason, action="restart")
    restarted_at = timezone.now().isoformat()
    cluster = _required_cluster(cluster_id)
    session = _active_workload_session_for_user(user, session_id, cluster, ref=ref, verb=K8sAdminAction.VERB_RESTART, policy_key="can_restart")
    assert_production_write_approved(session=session, cluster=cluster, ref=ref, action="restart")
    assert_admin_session_approved(session=session, action=K8sAdminAction.VERB_RESTART)
    provider = _required_rancher_provider(cluster)
    path = rancher_resource_path(provider, cluster, ref)
    assert_direct_admin_mutation_allowed(cluster=cluster, ref=ref, action="restart")
    patch = {"spec": {"template": {"metadata": {"annotations": {"kubectl.kubernetes.io/restartedAt": restarted_at}}}}}
    try:
        response = _provider_patch(provider, path, patch, transport=transport)
    except AdminResourceError as exc:
        _record_workload_action(
            user=user,
            session=session,
            cluster=cluster,
            ref=ref,
            verb=K8sAdminAction.VERB_RESTART,
            status=K8sAdminAction.STATUS_FAILED,
            request_payload={"reason": reason_value, "restarted_at": restarted_at},
            response_summary={"source": "provider_error", "error": str(exc)},
        )
        raise
    sanitized_response = sanitize_kubernetes_resource(response)
    ownership = build_admin_resource_ownership(cluster=cluster, ref=ref, resource=sanitized_response)
    action = _record_workload_action(
        user=user,
        session=session,
        cluster=cluster,
        ref=ref,
        verb=K8sAdminAction.VERB_RESTART,
        status=K8sAdminAction.STATUS_COMPLETED,
        request_payload={"reason": reason_value, "restarted_at": restarted_at},
        response_summary={
            "source": "rancher_kubernetes_restart",
            "restarted_at": restarted_at,
            "ownership_owner": ownership.get("owner"),
            "server_top_level_fields": sorted(sanitized_response.keys()),
        },
    )
    return _base_response(
        "restart",
        cluster,
        provider,
        ref,
        path,
        action,
        {
            "restarted_at": restarted_at,
            "resource": sanitized_response,
            "ownership": ownership,
        },
    )


def _active_workload_session_for_user(
    user,
    session_id: str,
    cluster: K8sCluster,
    *,
    ref: KubernetesResourceRef,
    verb: str,
    policy_key: str,
) -> K8sAdminSession:
    policy = kubernetes_permission_policy(user)
    if not policy.get(policy_key):
        code = f"native_{verb}_disabled" if policy["can_admin_write"] else "admin_write_required"
        raise AdminResourceError("Kubernetes workload mutation access is required.", code=code, status=403)
    try:
        session = K8sAdminSession.objects.select_related("user", "provider", "cluster").filter(session_id=session_id, user=user).first()
    except (TypeError, ValueError, ValidationError) as exc:
        raise AdminResourceError("Active write admin session is required.", code="admin_write_session_required", status=403) from exc
    if session is None:
        raise AdminResourceError("Active write admin session is required.", code="admin_write_session_required", status=403)
    session = refresh_admin_session_state(session)
    if session.status != K8sAdminSession.STATUS_ACTIVE:
        raise AdminResourceError("Write admin session is not active.", code="admin_write_session_not_active", status=403)
    if session.mode != K8sAdminSession.MODE_WRITE:
        raise AdminResourceError("Workload mutations require a write admin session.", code="write_session_required", status=403)
    if session.cluster_id and session.cluster_id != cluster.id:
        raise AdminResourceError("Admin session does not cover this cluster.", code="admin_session_cluster_mismatch", status=403)
    if verb not in set(session.allowed_verbs or []):
        raise AdminResourceError("Admin session does not allow this workload mutation.", code="admin_session_verb_denied", status=403)
    _check_session_scope(session, ref)
    return session


def _check_session_scope(session: K8sAdminSession, ref: KubernetesResourceRef) -> None:
    if ref.namespace:
        allowed_namespaces = set(session.allowed_namespaces or [])
        if "*" not in allowed_namespaces and ref.namespace not in allowed_namespaces:
            raise AdminResourceError("Admin session does not cover this namespace.", code="admin_session_namespace_denied", status=403)
    allowed_kinds = {str(item).lower() for item in session.allowed_kinds or []}
    if "*" not in allowed_kinds and ref.kind.lower() not in allowed_kinds:
        raise AdminResourceError("Admin session does not cover this resource kind.", code="admin_session_kind_denied", status=403)


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


def _clean_replicas(value: Any) -> int:
    try:
        replicas = int(value)
    except (TypeError, ValueError) as exc:
        raise AdminResourceError("replicas must be an integer.", code="replicas_invalid") from exc
    if replicas < 0 or replicas > int(getattr(settings, "KUBERNETES_ADMIN_SCALE_MAX_REPLICAS", 100)):
        raise AdminResourceError("replicas is outside the allowed range.", code="replicas_out_of_range")
    return replicas


def _required_reason(value: str, *, action: str) -> str:
    reason = str(value or "").strip()[:1000]
    if not reason:
        raise AdminResourceError(f"reason is required for {action}.", code="reason_required")
    return reason


def _record_workload_action(
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
        namespace=ref.namespace,
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
        raise AdminResourceError("Enabled Rancher provider is required for Admin Mode workload actions.", code="rancher_provider_required", status=409)
    return provider


def _base_response(operation: str, cluster: K8sCluster, provider: K8sProvider, ref: KubernetesResourceRef, path: str, action: K8sAdminAction, extra: dict[str, Any]) -> dict[str, Any]:
    return {
        "success": True,
        "mode": "admin_write_workload",
        "operation": operation,
        "mutates_state": True,
        "cluster": {"id": f"cluster_{cluster.id}", "name": cluster.name, "rancher_cluster_id": cluster.rancher_cluster_id},
        "provider": {"id": provider.id, "name": provider.name, "kind": provider.kind},
        "target": _target_payload(ref),
        "path": _public_path(path),
        "action": {"id": str(action.action_id), "status": action.status},
        "policy": {
            "mutates_state": True,
            "requires_active_admin_session": True,
            "requires_write_session": True,
            "blocked_actions": ["delete", "exec", "port_forward", "node_debug"],
        },
        **extra,
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
