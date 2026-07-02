from __future__ import annotations

import urllib.parse
from typing import Any

from kubernetes_ops.models import K8sAdminAction, K8sCluster, K8sProvider
from kubernetes_ops.services.admin_ownership import build_admin_resource_ownership
from kubernetes_ops.services.admin_resource_events import fetch_resource_events_snapshot
from kubernetes_ops.services.admin_resources import (
    AdminResourceError,
    KubernetesResourceRef,
    active_resource_session_for_user,
    build_resource_ref,
    cluster_for_value,
    rancher_resource_path,
    record_admin_resource_action,
    resource_was_redacted,
    sanitize_kubernetes_resource,
    secret_values_payload,
    secret_values_visible_for_request,
)
from kubernetes_ops.services.admin_resource_summary import build_resource_row_summary
from kubernetes_ops.services.describe import sanitize_metadata
from kubernetes_ops.services.logs import _redact_log_line
from kubernetes_ops.services.provider_clients import ProviderJsonClient, ProviderTransport

MAX_DETAIL_CONDITIONS = 12
MAX_DETAIL_KEYS = 40
MAX_DETAIL_EVENTS = 100


def get_cluster_resource_detail(
    *,
    user,
    session_id: str,
    cluster_id: str,
    api_version: str,
    kind: str,
    namespace: str = "",
    name: str = "",
    resource: str = "",
    include_events: bool | str = True,
    event_limit: int | str | None = None,
    include_managed_fields: bool | str = False,
    include_secret_values: bool | str = False,
    transport: ProviderTransport | None = None,
) -> dict[str, Any]:
    if not str(name or "").strip():
        raise AdminResourceError("name is required for resource detail.", code="name_required")
    cluster = _required_cluster(cluster_id)
    ref = build_resource_ref(api_version=api_version, kind=kind, namespace=namespace, name=name, resource=resource)
    session = active_resource_session_for_user(user, session_id, cluster, verb=K8sAdminAction.VERB_GET, namespace=ref.namespace, kind=ref.kind)
    events_requested = _bool_value(include_events)
    if events_requested:
        active_resource_session_for_user(user, session_id, cluster, verb=K8sAdminAction.VERB_LIST, namespace=ref.namespace, kind=ref.kind)
    provider = _required_rancher_provider(cluster)
    resource_path = rancher_resource_path(provider, cluster, ref)
    secret_values_visible = secret_values_visible_for_request(user, ref, include_secret_values)
    resource = sanitize_kubernetes_resource(
        _provider_get(provider, resource_path, transport=transport),
        include_managed_fields=_bool_value(include_managed_fields),
        allow_secret_values=secret_values_visible,
    )
    ownership = build_admin_resource_ownership(cluster=cluster, ref=ref, resource=resource)
    events = _events_section(
        provider=provider,
        cluster=cluster,
        ref=ref,
        requested=events_requested,
        limit=event_limit,
        transport=transport,
    )
    redacted = resource_was_redacted(resource) or bool(events.get("redacted"))
    describe = _describe_summary(resource)
    record_admin_resource_action(
        user=user,
        session=session,
        cluster=cluster,
        ref=ref,
        verb=K8sAdminAction.VERB_GET,
        status=K8sAdminAction.STATUS_COMPLETED,
        response_summary={
            "detail": True,
            "redacted": redacted,
            "events_requested": events_requested,
            "events_available": bool(events.get("available")),
            "event_count": int(events.get("event_count") or 0),
            "events_truncated": bool(events.get("truncated")),
            "include_managed_fields": _bool_value(include_managed_fields),
            "secret_values_requested": _bool_value(include_secret_values),
            "secret_values_visible": secret_values_visible,
            "describe_sections": list(describe.keys()),
            "ownership_owner": ownership.get("owner"),
        },
    )
    return {
        "success": True,
        "mode": "admin_read_only",
        "operation": "resource_detail",
        "cluster": _cluster_payload(cluster),
        "provider": _provider_payload(provider),
        "target": _target_payload(ref),
        "paths": {
            "resource": _public_path(resource_path),
            "events": events.get("path", ""),
        },
        "policy": {
            "mutates_state": False,
            "requires_active_admin_session": True,
            "streaming": False,
            "events_requested": events_requested,
            "blocked_actions": ["apply_yaml", "patch", "scale", "delete", "exec", "port_forward", "node_debug"],
        },
        "resource": resource,
        "summary": build_resource_row_summary(resource, ref=ref),
        "describe": describe,
        "ownership": ownership,
        "events": events,
        "secret_values": secret_values_payload(include_secret_values, secret_values_visible),
        "redacted": redacted,
    }


def _events_section(
    *,
    provider: K8sProvider,
    cluster: K8sCluster,
    ref: KubernetesResourceRef,
    requested: bool,
    limit: int | str | None,
    transport: ProviderTransport | None,
) -> dict[str, Any]:
    if not requested:
        return {"available": False, "requested": False, "events": [], "event_count": 0, "truncated": False, "redacted": False}
    try:
        snapshot = fetch_resource_events_snapshot(
            provider=provider,
            cluster=cluster,
            ref=ref,
            limit=limit or MAX_DETAIL_EVENTS,
            transport=transport,
        )
    except AdminResourceError as exc:
        return {
            "available": False,
            "requested": True,
            "events": [],
            "event_count": 0,
            "truncated": False,
            "redacted": False,
            "error": sanitize_metadata({"code": exc.code, "status": exc.status, "message": str(exc)[:300]}),
        }
    return {
        "available": True,
        "requested": True,
        "path": snapshot["public_path"],
        "field_selector": snapshot["field_selector"],
        "limit": snapshot["limit"],
        "events": snapshot["events"],
        "event_count": snapshot["event_count"],
        "truncated": snapshot["truncated"],
        "redacted": snapshot["redacted"],
        "source": "provider_events",
    }


def _describe_summary(resource: Any) -> dict[str, Any]:
    if not isinstance(resource, dict):
        return {}
    metadata = resource.get("metadata") if isinstance(resource.get("metadata"), dict) else {}
    spec = resource.get("spec") if isinstance(resource.get("spec"), dict) else {}
    status = resource.get("status") if isinstance(resource.get("status"), dict) else {}
    return sanitize_metadata(
        {
            "identity": {
                "api_version": str(resource.get("apiVersion") or "")[:80],
                "kind": str(resource.get("kind") or "")[:80],
                "namespace": str(metadata.get("namespace") or "")[:120],
                "name": str(metadata.get("name") or "")[:180],
                "uid": str(metadata.get("uid") or "")[:120],
                "resource_version": str(metadata.get("resourceVersion") or "")[:120],
                "generation": metadata.get("generation"),
                "creation_timestamp": str(metadata.get("creationTimestamp") or "")[:80],
            },
            "metadata": {
                "label_keys": _bounded_keys(metadata.get("labels")),
                "annotation_keys": _bounded_keys(metadata.get("annotations")),
                "owner_references": _owner_references(metadata.get("ownerReferences")),
            },
            "health": _health_summary(status),
            "shape": {
                "spec_keys": _bounded_keys(spec),
                "status_keys": _bounded_keys(status),
                "container_count": _container_count(spec),
                "init_container_count": len(spec.get("initContainers") or []) if isinstance(spec.get("initContainers"), list) else 0,
            },
        }
    )


def _health_summary(status: dict[str, Any]) -> dict[str, Any]:
    conditions = status.get("conditions") if isinstance(status.get("conditions"), list) else []
    return {
        "phase": _safe_text(status.get("phase"), 80),
        "reason": _safe_text(status.get("reason"), 160),
        "message": _safe_text(status.get("message"), 500),
        "replicas": status.get("replicas"),
        "ready_replicas": status.get("readyReplicas"),
        "available_replicas": status.get("availableReplicas"),
        "updated_replicas": status.get("updatedReplicas"),
        "conditions": [_condition_summary(item) for item in conditions[:MAX_DETAIL_CONDITIONS] if isinstance(item, dict)],
        "conditions_truncated": len(conditions) > MAX_DETAIL_CONDITIONS,
    }


def _condition_summary(condition: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": _safe_text(condition.get("type"), 120),
        "status": _safe_text(condition.get("status"), 40),
        "reason": _safe_text(condition.get("reason"), 160),
        "message": _safe_text(condition.get("message"), 500),
        "last_transition_time": _safe_text(condition.get("lastTransitionTime"), 80),
    }


def _owner_references(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    rows = []
    for item in value[:MAX_DETAIL_KEYS]:
        if not isinstance(item, dict):
            continue
        rows.append(
            {
                "api_version": str(item.get("apiVersion") or "")[:80],
                "kind": str(item.get("kind") or "")[:80],
                "name": str(item.get("name") or "")[:180],
                "controller": bool(item.get("controller")),
            }
        )
    return rows


def _bounded_keys(value: Any) -> list[str]:
    if not isinstance(value, dict):
        return []
    return sorted(str(key)[:180] for key in value.keys())[:MAX_DETAIL_KEYS]


def _container_count(spec: dict[str, Any]) -> int:
    containers = spec.get("containers")
    if isinstance(containers, list):
        return len(containers)
    template = spec.get("template") if isinstance(spec.get("template"), dict) else {}
    pod_spec = template.get("spec") if isinstance(template.get("spec"), dict) else {}
    containers = pod_spec.get("containers")
    return len(containers) if isinstance(containers, list) else 0


def _required_cluster(cluster_id: str) -> K8sCluster:
    cluster = cluster_for_value(cluster_id)
    if cluster is None:
        raise AdminResourceError("Cluster not found.", code="cluster_not_found", status=404)
    return cluster


def _required_rancher_provider(cluster: K8sCluster) -> K8sProvider:
    provider = cluster.rancher_provider
    if provider is None or not provider.enabled:
        raise AdminResourceError("Enabled Rancher provider is required for resource detail.", code="rancher_provider_required", status=409)
    return provider


def _provider_get(provider: K8sProvider, path: str, *, transport: ProviderTransport | None) -> dict[str, Any]:
    try:
        return ProviderJsonClient(provider, transport=transport).get(path)
    except Exception as exc:
        raise AdminResourceError(str(exc), code="provider_request_failed", status=502) from exc


def _bool_value(value: bool | str) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() not in {"", "0", "false", "no", "off"}


def _safe_text(value: object, max_length: int) -> str:
    return _redact_log_line(str(value or "").replace("\r", ""))[:max_length]


def _cluster_payload(cluster: K8sCluster) -> dict[str, Any]:
    return {"id": f"cluster_{cluster.id}", "name": cluster.name, "rancher_cluster_id": cluster.rancher_cluster_id}


def _provider_payload(provider: K8sProvider) -> dict[str, Any]:
    return {"id": provider.id, "name": provider.name, "kind": provider.kind}


def _target_payload(ref: KubernetesResourceRef) -> dict[str, str]:
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
