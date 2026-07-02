from __future__ import annotations

import urllib.parse
from typing import Any

from kubernetes_ops.models import K8sAdminAction, K8sCluster, K8sProvider
from kubernetes_ops.services.admin_resource_query import append_query
from kubernetes_ops.services.admin_resources import (
    AdminResourceError,
    KubernetesResourceRef,
    active_resource_session_for_user,
    build_resource_ref,
    rancher_resource_path,
    resource_was_redacted,
    sanitize_kubernetes_resource,
)
from kubernetes_ops.services.describe import sanitize_metadata
from kubernetes_ops.services.logs import _redact_log_line
from kubernetes_ops.services.normalizers import payload_items
from kubernetes_ops.services.provider_clients import ProviderJsonClient, ProviderTransport

MAX_RELATED_ITEMS = 30
MAX_KEYS = 40


def build_live_describe_related_section(
    *,
    user,
    session_id: str,
    provider: K8sProvider,
    cluster: K8sCluster,
    ref: KubernetesResourceRef,
    resource: dict[str, Any],
    requested: bool,
    transport: ProviderTransport | None,
) -> dict[str, Any]:
    base = {
        "requested": requested,
        "redacted": False,
        "skipped_reasons": [],
        "pods": {"available": False, "items": [], "item_count": 0},
        "controllers": {"available": False, "items": [], "item_count": 0},
    }
    if not requested:
        return base
    pods = _related_pods(user=user, session_id=session_id, provider=provider, cluster=cluster, ref=ref, resource=resource, transport=transport)
    controllers = _related_controllers(
        user=user,
        session_id=session_id,
        provider=provider,
        cluster=cluster,
        ref=ref,
        resource=resource,
        transport=transport,
    )
    return {
        "requested": True,
        "redacted": bool(pods.get("redacted")) or bool(controllers.get("redacted")),
        "skipped_reasons": [section.get("skipped_reason") for section in (pods, controllers) if section.get("skipped_reason")],
        "pods": pods,
        "controllers": controllers,
    }


def _related_pods(
    *,
    user,
    session_id: str,
    provider: K8sProvider,
    cluster: K8sCluster,
    ref: KubernetesResourceRef,
    resource: dict[str, Any],
    transport: ProviderTransport | None,
) -> dict[str, Any]:
    selector = _pod_selector(ref, resource)
    if not ref.namespace or not selector:
        return {"available": False, "items": [], "item_count": 0, "skipped_reason": "no_pod_selector"}
    if _selector_has_sensitive_key(selector):
        return {"available": False, "items": [], "item_count": 0, "skipped_reason": "selector_contains_sensitive_key"}
    pod_ref = build_resource_ref(api_version="v1", kind="Pod", namespace=ref.namespace)
    try:
        active_resource_session_for_user(user, session_id, cluster, verb=K8sAdminAction.VERB_LIST, namespace=ref.namespace, kind="Pod")
        path = append_query(
            rancher_resource_path(provider, cluster, pod_ref),
            {"labelSelector": _label_selector(selector), "limit": str(MAX_RELATED_ITEMS)},
        )
        raw = _provider_get(provider, path, transport=transport)
    except AdminResourceError as exc:
        return _skipped_related("pods", exc)
    raw_items = payload_items(raw)
    items = [sanitize_kubernetes_resource(item) for item in raw_items[:MAX_RELATED_ITEMS]]
    return {
        "available": True,
        "path": _public_path(path),
        "selector_keys": _bounded_keys(selector),
        "items": [_pod_summary(item) for item in items],
        "item_count": len(items),
        "truncated": len(raw_items) > MAX_RELATED_ITEMS,
        "redacted": any(resource_was_redacted(item) for item in items),
    }


def _related_controllers(
    *,
    user,
    session_id: str,
    provider: K8sProvider,
    cluster: K8sCluster,
    ref: KubernetesResourceRef,
    resource: dict[str, Any],
    transport: ProviderTransport | None,
) -> dict[str, Any]:
    if ref.kind != "Deployment" or not ref.namespace:
        return {"available": False, "items": [], "item_count": 0, "skipped_reason": "no_controller_context"}
    selector = _pod_selector(ref, resource)
    if not selector:
        return {"available": False, "items": [], "item_count": 0, "skipped_reason": "no_controller_selector"}
    if _selector_has_sensitive_key(selector):
        return {"available": False, "items": [], "item_count": 0, "skipped_reason": "selector_contains_sensitive_key"}
    replica_ref = build_resource_ref(api_version="apps/v1", kind="ReplicaSet", namespace=ref.namespace)
    try:
        active_resource_session_for_user(user, session_id, cluster, verb=K8sAdminAction.VERB_LIST, namespace=ref.namespace, kind="ReplicaSet")
        path = append_query(
            rancher_resource_path(provider, cluster, replica_ref),
            {"labelSelector": _label_selector(selector), "limit": str(MAX_RELATED_ITEMS)},
        )
        raw = _provider_get(provider, path, transport=transport)
    except AdminResourceError as exc:
        return _skipped_related("controllers", exc)
    raw_items = payload_items(raw)
    items = [sanitize_kubernetes_resource(item) for item in raw_items[:MAX_RELATED_ITEMS]]
    return {
        "available": True,
        "kind": "ReplicaSet",
        "path": _public_path(path),
        "selector_keys": _bounded_keys(selector),
        "items": [_controller_summary(item) for item in items],
        "item_count": len(items),
        "truncated": len(raw_items) > MAX_RELATED_ITEMS,
        "redacted": any(resource_was_redacted(item) for item in items),
    }


def _pod_summary(pod: dict[str, Any]) -> dict[str, Any]:
    metadata = pod.get("metadata") if isinstance(pod.get("metadata"), dict) else {}
    status = pod.get("status") if isinstance(pod.get("status"), dict) else {}
    spec = pod.get("spec") if isinstance(pod.get("spec"), dict) else {}
    container_statuses = status.get("containerStatuses") if isinstance(status.get("containerStatuses"), list) else []
    return sanitize_metadata(
        {
            "name": _safe_text(metadata.get("name"), 180),
            "namespace": _safe_text(metadata.get("namespace"), 120),
            "phase": _safe_text(status.get("phase"), 80),
            "ready": _pod_ready(status),
            "restart_count": sum(_safe_int(item.get("restartCount")) for item in container_statuses if isinstance(item, dict)),
            "node_name": _safe_text(spec.get("nodeName"), 180),
            "pod_ip": _safe_text(status.get("podIP"), 80),
            "resource_version": _safe_text(metadata.get("resourceVersion"), 120),
        }
    )


def _controller_summary(resource: dict[str, Any]) -> dict[str, Any]:
    metadata = resource.get("metadata") if isinstance(resource.get("metadata"), dict) else {}
    status = resource.get("status") if isinstance(resource.get("status"), dict) else {}
    return sanitize_metadata(
        {
            "kind": _safe_text(resource.get("kind"), 80),
            "name": _safe_text(metadata.get("name"), 180),
            "namespace": _safe_text(metadata.get("namespace"), 120),
            "replicas": status.get("replicas"),
            "ready_replicas": status.get("readyReplicas"),
            "available_replicas": status.get("availableReplicas"),
            "owner_references": _owner_references(metadata.get("ownerReferences")),
            "resource_version": _safe_text(metadata.get("resourceVersion"), 120),
        }
    )


def _pod_selector(ref: KubernetesResourceRef, resource: dict[str, Any]) -> dict[str, str]:
    spec = resource.get("spec") if isinstance(resource.get("spec"), dict) else {}
    if ref.kind == "Pod":
        labels = resource.get("metadata", {}).get("labels") if isinstance(resource.get("metadata"), dict) else {}
        return _string_map(labels)
    if ref.kind == "Service":
        return _string_map(spec.get("selector"))
    return _selector_from_spec(spec)


def _selector_from_spec(spec: dict[str, Any]) -> dict[str, str]:
    selector = spec.get("selector") if isinstance(spec.get("selector"), dict) else {}
    if "matchLabels" in selector:
        return _string_map(selector.get("matchLabels"))
    return _string_map(selector)


def _string_map(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    return {
        clean_key: clean_value
        for key, raw_value in value.items()
        if (clean_key := str(key or "").strip()[:120]) and (clean_value := str(raw_value or "").strip()[:240])
    }


def _label_selector(labels: dict[str, str]) -> str:
    return ",".join(f"{key}={value}" for key, value in sorted(labels.items()))


def _selector_has_sensitive_key(labels: dict[str, str]) -> bool:
    return any(_is_sensitive_key(key) for key in labels)


def _skipped_related(section: str, exc: AdminResourceError) -> dict[str, Any]:
    return {
        "available": False,
        "items": [],
        "item_count": 0,
        "skipped_reason": exc.code,
        "section": section,
        "error": sanitize_metadata({"code": exc.code, "status": exc.status, "message": str(exc)[:300]}),
    }


def _pod_ready(status: dict[str, Any]) -> bool:
    for condition in status.get("conditions") or []:
        if isinstance(condition, dict) and condition.get("type") == "Ready":
            return str(condition.get("status") or "").lower() == "true"
    return False


def _owner_references(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [
        {
            "api_version": _safe_text(item.get("apiVersion"), 80),
            "kind": _safe_text(item.get("kind"), 80),
            "name": _safe_text(item.get("name"), 180),
            "controller": bool(item.get("controller")),
        }
        for item in value[:MAX_KEYS]
        if isinstance(item, dict)
    ]


def _bounded_keys(value: Any) -> list[str]:
    if not isinstance(value, dict):
        return []
    return sorted(_safe_text(key, 180) for key in value.keys())[:MAX_KEYS]


def _provider_get(provider: K8sProvider, path: str, *, transport: ProviderTransport | None) -> dict[str, Any]:
    try:
        return ProviderJsonClient(provider, transport=transport).get(path)
    except Exception as exc:
        raise AdminResourceError(str(exc), code="provider_request_failed", status=502) from exc


def _safe_text(value: object, max_length: int) -> str:
    return _redact_log_line(str(value or "").replace("\r", ""))[:max_length]


def _safe_int(value: object) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return 0
    return parsed if parsed >= 0 else 0


def _is_sensitive_key(key: str) -> bool:
    normalized = str(key or "").replace("-", "_").lower()
    return any(part in normalized for part in ("token", "secret", "password", "credential", "kubeconfig", "authorization", "api_key", "apikey"))


def _public_path(path: str) -> str:
    parsed = urllib.parse.urlsplit(str(path or ""))
    return urllib.parse.urlunsplit(("", "", parsed.path or "/", "", ""))[:500]
