from __future__ import annotations

import json
import urllib.parse
from typing import Any

from django.conf import settings
from django.core.exceptions import ValidationError

from kubernetes_ops.models import K8sAdminAction, K8sAdminSession, K8sCluster, K8sProvider
from kubernetes_ops.permissions import kubernetes_permission_policy
from kubernetes_ops.services.admin_ownership import build_admin_resource_ownership
from kubernetes_ops.services.admin_owner_guard import assert_direct_admin_mutation_allowed
from kubernetes_ops.services.admin_resources import (
    AdminResourceError,
    KubernetesResourceRef,
    build_resource_ref,
    cluster_for_value,
    rancher_resource_path,
    resource_was_redacted,
    sanitize_kubernetes_resource,
)
from kubernetes_ops.services.admin_sessions import refresh_admin_session_state
from kubernetes_ops.services.admin_write_approval import assert_admin_session_approved, assert_production_write_approved
from kubernetes_ops.services.describe import sanitize_metadata
from kubernetes_ops.services.provider_clients import KubernetesProviderError, ProviderJsonClient, ProviderTransport


PATCH_TYPES = {
    "merge": "application/merge-patch+json",
    "strategic": "application/strategic-merge-patch+json",
    "json": "application/json-patch+json",
}


def patch_kubernetes_resource(
    *,
    user,
    session_id: str,
    cluster_id: str,
    api_version: str,
    kind: str,
    namespace: str,
    name: str,
    patch_body: Any,
    reason: str,
    resource: str = "",
    patch_type: str = "merge",
    transport: ProviderTransport | None = None,
) -> dict[str, Any]:
    if not bool(getattr(settings, "KUBERNETES_ADMIN_NATIVE_PATCH_ENABLED", False)):
        raise AdminResourceError("Native Kubernetes patch is disabled by policy.", code="native_patch_disabled", status=403)
    ref = build_resource_ref(api_version=api_version, kind=kind, namespace=namespace, name=name, resource=resource)
    if not ref.name:
        raise AdminResourceError("name is required for patch.", code="resource_name_required")
    patch_kind, content_type, body = _clean_patch_body(patch_body, patch_type=patch_type)
    reason_value = _required_reason(reason)
    cluster = _required_cluster(cluster_id)
    session = _active_patch_session_for_user(user, session_id, cluster, ref=ref)
    assert_production_write_approved(session=session, cluster=cluster, ref=ref, action="patch")
    assert_admin_session_approved(session=session, action=K8sAdminAction.VERB_PATCH)
    provider = _required_rancher_provider(cluster)
    path = rancher_resource_path(provider, cluster, ref)
    request_summary = _patch_request_summary(ref, body=body, patch_type=patch_kind, reason=reason_value)
    assert_direct_admin_mutation_allowed(cluster=cluster, ref=ref, action="patch")

    try:
        response = ProviderJsonClient(provider, transport=transport).request(
            "PATCH",
            path,
            body=body,
            extra_headers={"Content-Type": content_type, "Accept": "application/json"},
        )
    except (KubernetesProviderError, ValueError, KeyError) as exc:
        _record_patch_action(
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
    redacted = bool(request_summary.get("redacted")) or resource_was_redacted(sanitized_response)
    ownership = build_admin_resource_ownership(cluster=cluster, ref=ref, resource=sanitized_response)
    action = _record_patch_action(
        user=user,
        session=session,
        cluster=cluster,
        ref=ref,
        status=K8sAdminAction.STATUS_COMPLETED,
        request_summary=request_summary,
        response_summary={
            "source": "rancher_kubernetes_patch",
            "patch_type": patch_kind,
            "redacted": redacted,
            "ownership_owner": ownership.get("owner"),
            "server_top_level_fields": sorted(sanitized_response.keys()),
        },
    )
    return {
        "success": True,
        "mode": "admin_write_patch",
        "operation": "patch",
        "mutates_state": True,
        "cluster": _cluster_payload(cluster),
        "provider": _provider_payload(provider),
        "target": _target_payload(ref),
        "path": _public_path(path),
        "patch_type": patch_kind,
        "resource": sanitized_response,
        "redacted": redacted,
        "ownership": ownership,
        "action": {"id": str(action.action_id), "status": action.status},
        "policy": {
            "mutates_state": True,
            "requires_active_admin_session": True,
            "requires_write_session": True,
            "requires_reason": True,
            "blocked_actions": ["delete", "exec", "port_forward", "node_debug"],
        },
    }


def _active_patch_session_for_user(user, session_id: str, cluster: K8sCluster, *, ref: KubernetesResourceRef) -> K8sAdminSession:
    policy = kubernetes_permission_policy(user)
    if not policy.get("can_patch"):
        code = "native_patch_disabled" if policy["can_admin_write"] else "admin_write_required"
        raise AdminResourceError("Kubernetes patch access is required.", code=code, status=403)
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
        raise AdminResourceError("Patch requires a write admin session.", code="write_session_required", status=403)
    if session.cluster_id and session.cluster_id != cluster.id:
        raise AdminResourceError("Admin session does not cover this cluster.", code="admin_session_cluster_mismatch", status=403)
    if K8sAdminAction.VERB_PATCH not in set(session.allowed_verbs or []):
        raise AdminResourceError("Admin session does not allow patch.", code="admin_session_verb_denied", status=403)
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


def _clean_patch_body(value: Any, *, patch_type: str) -> tuple[str, str, Any]:
    normalized_type = str(patch_type or "merge").strip().lower()
    if normalized_type not in PATCH_TYPES:
        raise AdminResourceError("patch_type must be merge, strategic, or json.", code="patch_type_invalid")
    if normalized_type == "json":
        if not isinstance(value, list):
            raise AdminResourceError("JSON patch body must be a list of operations.", code="patch_body_invalid")
        body = value
    else:
        if not isinstance(value, dict):
            raise AdminResourceError("Patch body must be an object.", code="patch_body_invalid")
        body = value
    try:
        encoded_size = len(json.dumps(body, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))
    except (TypeError, ValueError) as exc:
        raise AdminResourceError("Patch body must be JSON serializable.", code="patch_body_invalid") from exc
    max_bytes = int(getattr(settings, "KUBERNETES_ADMIN_PATCH_MAX_BODY_BYTES", 65536))
    if encoded_size <= 0 or encoded_size > max_bytes:
        raise AdminResourceError("Patch body is outside the allowed size.", code="patch_body_size_invalid", payload={"max_bytes": max_bytes})
    return normalized_type, PATCH_TYPES[normalized_type], body


def _patch_request_summary(ref: KubernetesResourceRef, *, body: Any, patch_type: str, reason: str) -> dict[str, Any]:
    if isinstance(body, dict):
        shape = {
            "body_shape": "object",
            "top_level_fields": sorted(str(key)[:120] for key in body.keys()),
        }
    else:
        ops = []
        for item in body[:50]:
            if isinstance(item, dict):
                ops.append({"op": str(item.get("op") or "")[:40], "path": str(item.get("path") or "")[:240]})
        shape = {"body_shape": "json_patch", "operation_count": len(body), "operations": ops}
    return {
        "target": _target_payload(ref),
        "reason": reason,
        "patch_type": patch_type,
        "redacted": _patch_body_is_sensitive(ref, body),
        **shape,
    }


def _patch_body_is_sensitive(ref: KubernetesResourceRef, body: Any) -> bool:
    if ref.kind.lower() == "secret":
        return True
    text = str(sanitize_metadata(body)).lower()
    return "[redacted]" in text


def _required_reason(value: str) -> str:
    reason = str(value or "").strip()[:1000]
    if not reason:
        raise AdminResourceError("reason is required for patch.", code="reason_required")
    return reason


def _record_patch_action(
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
        verb=K8sAdminAction.VERB_PATCH,
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
        raise AdminResourceError("Enabled Rancher provider is required for Admin Mode patch.", code="rancher_provider_required", status=409)
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
