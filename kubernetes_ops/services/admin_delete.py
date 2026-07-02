from __future__ import annotations

import urllib.parse
from typing import Any

from django.conf import settings
from django.core.exceptions import ValidationError

from kubernetes_ops.models import K8sAdminAction, K8sAdminSession, K8sCluster, K8sProvider
from kubernetes_ops.permissions import kubernetes_permission_policy
from kubernetes_ops.services.admin_owner_guard import assert_direct_admin_mutation_allowed
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


PROTECTED_CLUSTER_KINDS = {
    "Namespace",
    "Node",
    "PersistentVolume",
    "CustomResourceDefinition",
    "ClusterRole",
    "ClusterRoleBinding",
    "StorageClass",
    "APIService",
    "IngressClass",
    "PriorityClass",
    "RuntimeClass",
    "MutatingWebhookConfiguration",
    "ValidatingWebhookConfiguration",
}
DEFAULT_PROTECTED_NAMESPACES = {
    "argocd",
    "cattle-fleet-local-system",
    "cattle-fleet-system",
    "cattle-system",
    "cert-manager",
    "devtroncd",
    "ingress-nginx",
    "kube-node-lease",
    "kube-public",
    "kube-system",
    "local",
    "logging",
    "monitoring",
}
PROPAGATION_POLICIES = {"Foreground", "Background", "Orphan"}


def delete_kubernetes_resource(
    *,
    user,
    session_id: str,
    cluster_id: str,
    api_version: str,
    kind: str,
    namespace: str,
    name: str,
    confirmation: str,
    reason: str,
    resource: str = "",
    propagation_policy: str = "",
    transport: ProviderTransport | None = None,
) -> dict[str, Any]:
    if not bool(getattr(settings, "KUBERNETES_ADMIN_NATIVE_DELETE_ENABLED", False)):
        raise AdminResourceError("Native Kubernetes delete is disabled by policy.", code="native_delete_disabled", status=403)
    ref = build_resource_ref(api_version=api_version, kind=kind, namespace=namespace, name=name, resource=resource)
    _validate_delete_target(ref)
    reason_value = _required_reason(reason)
    expected_confirmation = expected_delete_confirmation(ref)
    if str(confirmation or "").strip() != expected_confirmation:
        raise AdminResourceError(
            "Exact delete confirmation is required.",
            code="delete_confirmation_mismatch",
            status=409,
            payload={"expected_confirmation": expected_confirmation},
        )
    propagation = _clean_propagation_policy(propagation_policy)
    cluster = _required_cluster(cluster_id)
    session = _active_delete_session_for_user(user, session_id, cluster, ref=ref)
    assert_production_write_approved(session=session, cluster=cluster, ref=ref, action="delete")
    assert_admin_session_approved(session=session, action=K8sAdminAction.VERB_DELETE)
    provider = _required_rancher_provider(cluster)
    path = rancher_resource_path(provider, cluster, ref)
    assert_direct_admin_mutation_allowed(cluster=cluster, ref=ref, action="delete")
    request_summary = {
        "target": _target_payload(ref),
        "reason": reason_value,
        "confirmation": "matched",
        "expected_confirmation": expected_confirmation,
        "propagation_policy": propagation or "server_default",
    }

    try:
        response = ProviderJsonClient(provider, transport=transport).request(
            "DELETE",
            path,
            body=_delete_options(propagation),
            extra_headers={"Accept": "application/json"},
        )
    except (KubernetesProviderError, ValueError, KeyError) as exc:
        _record_delete_action(
            user=user,
            session=session,
            cluster=cluster,
            ref=ref,
            status=K8sAdminAction.STATUS_FAILED,
            request_summary=request_summary,
            response_summary={"source": "provider_error", "error": str(exc)},
        )
        raise AdminResourceError(str(exc), code="provider_request_failed", status=502) from exc

    sanitized_response = sanitize_kubernetes_resource(response)
    action = _record_delete_action(
        user=user,
        session=session,
        cluster=cluster,
        ref=ref,
        status=K8sAdminAction.STATUS_COMPLETED,
        request_summary=request_summary,
        response_summary={
            "source": "rancher_kubernetes_delete",
            "response_kind": str(sanitized_response.get("kind") or ""),
            "response_status": str(sanitized_response.get("status") or ""),
            "propagation_policy": propagation or "server_default",
            "server_top_level_fields": sorted(sanitized_response.keys()),
        },
    )
    return {
        "success": True,
        "mode": "admin_write_delete",
        "operation": "delete",
        "mutates_state": True,
        "cluster": _cluster_payload(cluster),
        "provider": _provider_payload(provider),
        "target": _target_payload(ref),
        "path": _public_path(path),
        "confirmation": {"matched": True, "expected": expected_confirmation},
        "propagation_policy": propagation or "server_default",
        "result": sanitized_response,
        "action": {"id": str(action.action_id), "status": action.status},
        "policy": {
            "mutates_state": True,
            "requires_active_admin_session": True,
            "requires_write_session": True,
            "requires_reason": True,
            "requires_exact_confirmation": True,
            "protected_namespaces": sorted(_protected_namespaces()),
            "blocked_kinds": sorted(PROTECTED_CLUSTER_KINDS),
            "blocked_actions": ["exec", "port_forward", "node_debug"],
        },
    }


def expected_delete_confirmation(ref: KubernetesResourceRef) -> str:
    if ref.namespace:
        return f"delete {ref.kind} {ref.namespace}/{ref.name}"
    return f"delete {ref.kind} {ref.name}"


def protected_delete_namespaces() -> set[str]:
    return _protected_namespaces()


def _active_delete_session_for_user(user, session_id: str, cluster: K8sCluster, *, ref: KubernetesResourceRef) -> K8sAdminSession:
    policy = kubernetes_permission_policy(user)
    if not policy.get("can_delete"):
        code = "native_delete_disabled" if policy["can_admin_write"] else "admin_write_required"
        raise AdminResourceError("Kubernetes delete access is required.", code=code, status=403)
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
        raise AdminResourceError("Delete requires a write admin session.", code="write_session_required", status=403)
    if session.cluster_id and session.cluster_id != cluster.id:
        raise AdminResourceError("Admin session does not cover this cluster.", code="admin_session_cluster_mismatch", status=403)
    if K8sAdminAction.VERB_DELETE not in set(session.allowed_verbs or []):
        raise AdminResourceError("Admin session does not allow delete.", code="admin_session_verb_denied", status=403)
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


def _validate_delete_target(ref: KubernetesResourceRef) -> None:
    if not ref.name:
        raise AdminResourceError("name is required for delete.", code="resource_name_required")
    if ref.kind in PROTECTED_CLUSTER_KINDS:
        raise AdminResourceError("This resource kind cannot be deleted through Admin Mode.", code="delete_kind_blocked", status=403)
    if not ref.namespace:
        raise AdminResourceError("Cluster-scoped deletes are blocked by Admin Mode.", code="delete_cluster_scope_blocked", status=403)
    if ref.namespace in _protected_namespaces():
        raise AdminResourceError("Deletes in protected namespaces are blocked by Admin Mode.", code="delete_namespace_protected", status=403)


def _protected_namespaces() -> set[str]:
    configured = getattr(settings, "KUBERNETES_ADMIN_DELETE_PROTECTED_NAMESPACES", None)
    if isinstance(configured, (list, tuple, set)):
        values = configured
    else:
        values = str(configured or "").split(",")
    cleaned = {str(item).strip() for item in values if str(item).strip()}
    return cleaned or set(DEFAULT_PROTECTED_NAMESPACES)


def _clean_propagation_policy(value: str) -> str:
    policy = str(value or "").strip()
    if not policy:
        return ""
    normalized = policy[:1].upper() + policy[1:].lower()
    if normalized not in PROPAGATION_POLICIES:
        raise AdminResourceError("propagation_policy must be Foreground, Background, or Orphan.", code="propagation_policy_invalid")
    return normalized


def _delete_options(propagation_policy: str) -> dict[str, Any] | None:
    if not propagation_policy:
        return None
    return {"apiVersion": "v1", "kind": "DeleteOptions", "propagationPolicy": propagation_policy}


def _required_reason(value: str) -> str:
    reason = str(value or "").strip()[:1000]
    if not reason:
        raise AdminResourceError("reason is required for delete.", code="reason_required")
    return reason


def _record_delete_action(
    *,
    user,
    session: K8sAdminSession,
    cluster: K8sCluster,
    ref: KubernetesResourceRef,
    status: str,
    request_summary: dict[str, Any],
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
        verb=K8sAdminAction.VERB_DELETE,
        status=status,
        request_payload_sanitized=sanitize_metadata(request_summary),
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
        raise AdminResourceError("Enabled Rancher provider is required for Admin Mode delete.", code="rancher_provider_required", status=409)
    return provider


def _cluster_payload(cluster: K8sCluster) -> dict[str, Any]:
    return {"id": f"cluster_{cluster.id}", "name": cluster.name, "rancher_cluster_id": cluster.rancher_cluster_id}


def _provider_payload(provider: K8sProvider) -> dict[str, Any]:
    return {"id": provider.id, "name": provider.name, "kind": provider.kind}


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
