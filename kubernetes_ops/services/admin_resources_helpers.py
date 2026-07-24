from __future__ import annotations

import urllib.parse
from dataclasses import dataclass
from typing import Any

from django.core.exceptions import ValidationError
from django.db.models import Q

from kubernetes_ops.models import K8sAdminAction, K8sAdminSession, K8sCluster, K8sProvider
from kubernetes_ops.permissions import kubernetes_permission_policy
from kubernetes_ops.services.admin_resource_registry import (
    COMMON_RESOURCES,
    display_kind,
    pluralize_kind,
)
from kubernetes_ops.services.admin_secret_values import SecretValueAccessError
from kubernetes_ops.services.admin_secret_values import (
    secret_values_visible_for_request as _secret_values_visible_for_request,
)
from kubernetes_ops.services.admin_sessions import refresh_admin_session_state
from kubernetes_ops.services.describe import sanitize_metadata
from kubernetes_ops.services.provider_clients import ProviderJsonClient, ProviderTransport, provider_path


class AdminResourceError(ValueError):
    def __init__(self, message: str, *, code: str, status: int = 400, payload: dict[str, Any] | None = None):
        super().__init__(message)
        self.code, self.status, self.payload = code, status, payload or {}


@dataclass(frozen=True)
class KubernetesResourceRef:
    api_version: str
    kind: str
    resource: str
    namespace: str = ""
    name: str = ""


MAX_LIST_ITEMS = 250
READ_VERBS = {"get", "list", "watch", "logs", "yaml"}


def cluster_for_value(cluster_id: str) -> K8sCluster | None:
    value = str(cluster_id or "").strip()
    numeric = value.removeprefix("cluster_")
    query = Q(name=value) | Q(rancher_cluster_id=value) | Q(devtron_cluster_id=value)
    if numeric.isdigit():
        query |= Q(id=int(numeric))
    return K8sCluster.objects.filter(query).select_related("rancher_provider").first()


def active_resource_session_for_user(
    user, session_id: str, cluster: K8sCluster, *, verb: str, namespace: str = "", kind: str = ""
) -> K8sAdminSession:
    if not (policy := kubernetes_permission_policy(user))["admin_mode_enabled"]:
        raise AdminResourceError("Kubernetes Admin Mode is disabled.", code="admin_mode_disabled", status=403)
    if not (policy["can_admin_read"] or policy["can_admin_write"] or policy["can_break_glass"]):
        raise AdminResourceError(
            "Kubernetes Admin Mode read access is required.", code="admin_read_required", status=403
        )
    try:
        session = (
            K8sAdminSession.objects.select_related("user", "provider", "cluster")
            .filter(session_id=session_id, user=user)
            .first()
        )
    except (TypeError, ValueError, ValidationError) as exc:
        raise AdminResourceError(
            "Active admin session is required.", code="admin_session_required", status=403
        ) from exc
    if session is None:
        raise AdminResourceError("Active admin session is required.", code="admin_session_required", status=403)
    session = refresh_admin_session_state(session)
    if session.status != K8sAdminSession.STATUS_ACTIVE:
        raise AdminResourceError("Admin session is not active.", code="admin_session_not_active", status=403)
    if session.cluster_id and session.cluster_id != cluster.id:
        raise AdminResourceError(
            "Admin session does not cover this cluster.", code="admin_session_cluster_mismatch", status=403
        )
    if verb not in set(session.allowed_verbs or []):
        raise AdminResourceError(
            "Admin session does not allow this verb.", code="admin_session_verb_denied", status=403
        )
    if verb not in READ_VERBS:
        raise AdminResourceError(
            "Only read verbs are supported by this endpoint.", code="verb_not_read_only", status=403
        )
    if namespace:
        allowed_namespaces = set(session.allowed_namespaces or [])
        if "*" not in allowed_namespaces and namespace not in allowed_namespaces:
            raise AdminResourceError(
                "Admin session does not cover this namespace.", code="admin_session_namespace_denied", status=403
            )
    if kind:
        allowed_kinds = {str(item).lower() for item in session.allowed_kinds or []}
        if "*" not in allowed_kinds and kind.lower() not in allowed_kinds:
            raise AdminResourceError(
                "Admin session does not cover this resource kind.", code="admin_session_kind_denied", status=403
            )
    return session


def build_resource_ref(
    *, api_version: str, kind: str, namespace: str = "", name: str = "", resource: str = ""
) -> KubernetesResourceRef:
    version = str(api_version or "").strip() or "v1"
    normalized_kind = display_kind(kind)
    if not normalized_kind:
        raise AdminResourceError("kind is required.", code="kind_required")
    configured = COMMON_RESOURCES.get((version, normalized_kind), {})
    resource_name = str(resource or configured.get("resource") or pluralize_kind(normalized_kind)).strip().lower()
    return KubernetesResourceRef(
        api_version=version,
        kind=normalized_kind,
        resource=resource_name,
        namespace=str(namespace or "").strip(),
        name=str(name or "").strip(),
    )


def rancher_resource_path(provider: K8sProvider, cluster: K8sCluster, ref: KubernetesResourceRef) -> str:
    base = rancher_api_path(provider, cluster, ref.api_version)
    namespaced = _is_namespaced(ref)
    parts = [base.rstrip("/")]
    if namespaced:
        if not ref.namespace:
            raise AdminResourceError("namespace is required for namespaced resources.", code="namespace_required")
        parts.extend(["namespaces", _quote(ref.namespace)])
    parts.append(_quote(ref.resource))
    if ref.name:
        parts.append(_quote(ref.name))
    return "/".join(parts)


def rancher_api_path(provider: K8sProvider, cluster: K8sCluster, api_version: str) -> str:
    version = str(api_version or "v1").strip()
    prefix = _proxy_prefix(provider, cluster)
    if "/" not in version:
        return f"{prefix}/api/{_quote(version)}"
    group, _, version_name = version.partition("/")
    return f"{prefix}/apis/{_quote(group)}/{_quote(version_name)}"


def secret_values_visible_for_request(user, ref: KubernetesResourceRef, requested: bool | str) -> bool:
    try:
        return _secret_values_visible_for_request(user, ref, requested)
    except SecretValueAccessError as exc:
        raise AdminResourceError(
            str(exc),
            code=exc.code,
            status=exc.status,
            payload=exc.payload,
        ) from exc


def record_admin_resource_action(
    *,
    user,
    session: K8sAdminSession,
    cluster: K8sCluster,
    ref: KubernetesResourceRef,
    verb: str,
    status: str,
    response_summary: dict[str, Any] | None = None,
) -> K8sAdminAction:
    response_summary = response_summary or {}
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
        request_payload_sanitized={
            "api_version": ref.api_version,
            "kind": ref.kind,
            "resource": ref.resource,
            "namespace": ref.namespace,
            "name": ref.name,
        },
        response_summary=_safe_response_summary(response_summary),
    )


def _safe_response_summary(value: dict[str, Any]) -> dict[str, Any]:
    summary = sanitize_metadata(value)
    if not isinstance(summary, dict):
        return {}
    for key in ("secret_values_requested", "secret_values_visible"):
        original = value.get(key)
        if isinstance(original, bool):
            summary[key] = original
    return summary


def _required_cluster(cluster_id: str) -> K8sCluster:
    cluster = cluster_for_value(cluster_id)
    if cluster is None:
        raise AdminResourceError("Cluster not found.", code="cluster_not_found", status=404)
    return cluster


def _required_rancher_provider(cluster: K8sCluster) -> K8sProvider:
    provider = cluster.rancher_provider
    if provider is None or not provider.enabled:
        raise AdminResourceError(
            "Enabled Rancher provider is required for live Admin Mode reads.",
            code="rancher_provider_required",
            status=409,
        )
    return provider


def _provider_get(provider: K8sProvider, path: str, *, transport: ProviderTransport | None) -> dict[str, Any]:
    try:
        return ProviderJsonClient(provider, transport=transport).get(path)
    except Exception as exc:
        raise AdminResourceError(str(exc), code="provider_request_failed", status=502) from exc


def _base_response(
    operation: str,
    cluster: K8sCluster,
    provider: K8sProvider,
    ref: KubernetesResourceRef,
    path: str,
    extra: dict[str, Any],
) -> dict[str, Any]:
    return {
        "success": True,
        "mode": "admin_read_only",
        "operation": operation,
        "cluster": _cluster_payload(cluster),
        "provider": _provider_payload(provider),
        "target": {
            "api_version": ref.api_version,
            "kind": ref.kind,
            "resource": ref.resource,
            "namespace": ref.namespace,
            "name": ref.name,
        },
        "path": _public_path(path),
        "policy": {
            "mutates_state": False,
            "requires_active_admin_session": True,
            "blocked_actions": ["apply_yaml", "patch", "scale", "delete", "exec", "port_forward", "node_debug"],
        },
        **extra,
    }


def _cluster_payload(cluster: K8sCluster) -> dict[str, Any]:
    return {"id": f"cluster_{cluster.id}", "name": cluster.name, "rancher_cluster_id": cluster.rancher_cluster_id}


def _provider_payload(provider: K8sProvider) -> dict[str, Any]:
    return {"id": provider.id, "name": provider.name, "kind": provider.kind}


def _proxy_prefix(provider: K8sProvider, cluster: K8sCluster) -> str:
    template = provider_path(provider, "k8s_proxy_prefix", "/k8s/clusters/{cluster_id}")
    cluster_ref = cluster.rancher_cluster_id or str(cluster.id)
    return template.format(cluster_id=_quote(cluster_ref), cluster_name=_quote(cluster.name)).rstrip("/")


def _is_namespaced(ref: KubernetesResourceRef) -> bool:
    configured = COMMON_RESOURCES.get((ref.api_version, ref.kind))
    if configured is not None:
        return bool(configured["namespaced"])
    return bool(ref.namespace)


def _quote(value: str) -> str:
    return urllib.parse.quote(str(value), safe="")


def _public_path(path: str) -> str:
    parsed = urllib.parse.urlsplit(str(path or ""))
    return urllib.parse.urlunsplit(("", "", parsed.path or "/", "", ""))[:500]


def _resource_name(value: dict[str, Any]) -> str:
    metadata = value.get("metadata") if isinstance(value, dict) else {}
    return str(metadata.get("name") or "") if isinstance(metadata, dict) else ""
