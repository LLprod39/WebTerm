from __future__ import annotations

import urllib.parse
from typing import Any

from kubernetes_ops.models import K8sAdminAction, K8sCluster, K8sProvider
from kubernetes_ops.services.admin_resource_describe_related import build_live_describe_related_section
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
)
from kubernetes_ops.services.describe import sanitize_metadata
from kubernetes_ops.services.logs import _redact_log_line
from kubernetes_ops.services.provider_clients import ProviderJsonClient, ProviderTransport

MAX_DESCRIBE_EVENTS = 50
MAX_CONDITIONS = 12
MAX_KEYS = 40


def get_cluster_resource_live_describe(
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
    include_related: bool | str = True,
    event_limit: int | str | None = None,
    transport: ProviderTransport | None = None,
) -> dict[str, Any]:
    if not str(name or "").strip():
        raise AdminResourceError("name is required for live describe.", code="name_required")
    cluster = _required_cluster(cluster_id)
    ref = build_resource_ref(api_version=api_version, kind=kind, namespace=namespace, name=name, resource=resource)
    session = active_resource_session_for_user(
        user,
        session_id,
        cluster,
        verb=K8sAdminAction.VERB_GET,
        namespace=ref.namespace,
        kind=ref.kind,
    )
    provider = _required_rancher_provider(cluster)
    resource_path = rancher_resource_path(provider, cluster, ref)
    resource = sanitize_kubernetes_resource(_provider_get(provider, resource_path, transport=transport))
    events = _events_section(
        user=user,
        session_id=session_id,
        provider=provider,
        cluster=cluster,
        ref=ref,
        requested=_bool_value(include_events),
        limit=event_limit,
        transport=transport,
    )
    related = build_live_describe_related_section(
        user=user,
        session_id=session_id,
        provider=provider,
        cluster=cluster,
        ref=ref,
        resource=resource,
        requested=_bool_value(include_related),
        transport=transport,
    )
    redacted = resource_was_redacted(resource) or bool(events.get("redacted")) or bool(related.get("redacted"))
    summary = _resource_summary(resource)
    record_admin_resource_action(
        user=user,
        session=session,
        cluster=cluster,
        ref=ref,
        verb=K8sAdminAction.VERB_GET,
        status=K8sAdminAction.STATUS_COMPLETED,
        response_summary={
            "live_describe": True,
            "redacted": redacted,
            "events_requested": bool(events.get("requested")),
            "event_count": int(events.get("event_count") or 0),
            "related_requested": bool(related.get("requested")),
            "related_pod_count": int(related.get("pods", {}).get("item_count") or 0),
            "related_controller_count": int(related.get("controllers", {}).get("item_count") or 0),
            "related_skipped": related.get("skipped_reasons", []),
            "summary_sections": list(summary.keys()),
        },
    )
    return {
        "success": True,
        "mode": "admin_read_only",
        "operation": "resource_live_describe",
        "cluster": _cluster_payload(cluster),
        "provider": _provider_payload(provider),
        "target": _target_payload(ref),
        "paths": {
            "resource": _public_path(resource_path),
            "events": events.get("path", ""),
            "related_pods": related.get("pods", {}).get("path", ""),
            "related_controllers": related.get("controllers", {}).get("path", ""),
        },
        "policy": {
            "mutates_state": False,
            "requires_active_admin_session": True,
            "streaming": False,
            "live_provider_reads": True,
            "blocked_actions": ["apply_yaml", "patch", "scale", "delete", "exec", "port_forward", "node_debug"],
        },
        "summary": summary,
        "events": events,
        "related": related,
        "redacted": redacted,
    }


def _events_section(
    *,
    user,
    session_id: str,
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
        active_resource_session_for_user(user, session_id, cluster, verb=K8sAdminAction.VERB_LIST, namespace=ref.namespace, kind=ref.kind)
        snapshot = fetch_resource_events_snapshot(
            provider=provider,
            cluster=cluster,
            ref=ref,
            limit=limit or MAX_DESCRIBE_EVENTS,
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
            "skipped_reason": exc.code,
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


def _resource_summary(resource: dict[str, Any]) -> dict[str, Any]:
    metadata = resource.get("metadata") if isinstance(resource.get("metadata"), dict) else {}
    spec = resource.get("spec") if isinstance(resource.get("spec"), dict) else {}
    status = resource.get("status") if isinstance(resource.get("status"), dict) else {}
    return sanitize_metadata(
        {
            "identity": {
                "api_version": _safe_text(resource.get("apiVersion"), 80),
                "kind": _safe_text(resource.get("kind"), 80),
                "namespace": _safe_text(metadata.get("namespace"), 120),
                "name": _safe_text(metadata.get("name"), 180),
                "uid": _safe_text(metadata.get("uid"), 120),
                "resource_version": _safe_text(metadata.get("resourceVersion"), 120),
                "generation": metadata.get("generation"),
                "creation_timestamp": _safe_text(metadata.get("creationTimestamp"), 80),
            },
            "metadata": {
                "label_keys": _bounded_keys(metadata.get("labels")),
                "annotation_keys": _bounded_keys(metadata.get("annotations")),
                "owner_references": _owner_references(metadata.get("ownerReferences")),
            },
            "spec": {
                "replicas": spec.get("replicas"),
                "strategy": _safe_text(_nested(spec, "strategy.type"), 80),
                "selector_keys": _bounded_keys(_selector_from_spec(spec)),
                "container_count": _container_count(spec),
                "container_names": _container_names(spec),
                "service_type": _safe_text(spec.get("type"), 80),
                "ports": _ports(spec.get("ports")),
            },
            "status": {
                "phase": _safe_text(status.get("phase"), 80),
                "reason": _safe_text(status.get("reason"), 160),
                "message": _safe_text(status.get("message"), 500),
                "observed_generation": status.get("observedGeneration"),
                "replicas": status.get("replicas"),
                "ready_replicas": status.get("readyReplicas"),
                "available_replicas": status.get("availableReplicas"),
                "updated_replicas": status.get("updatedReplicas"),
                "conditions": [_condition_summary(item) for item in _conditions(status)],
                "conditions_truncated": len(status.get("conditions") or []) > MAX_CONDITIONS if isinstance(status.get("conditions"), list) else False,
            },
        }
    )


def _selector_from_spec(spec: dict[str, Any]) -> dict[str, str]:
    selector = spec.get("selector") if isinstance(spec.get("selector"), dict) else {}
    if "matchLabels" in selector:
        return _string_map(selector.get("matchLabels"))
    return _string_map(selector)


def _string_map(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    rows: dict[str, str] = {}
    for key, raw_value in value.items():
        clean_key = str(key or "").strip()[:120]
        clean_value = str(raw_value or "").strip()[:240]
        if clean_key and clean_value:
            rows[clean_key] = clean_value
    return rows


def _conditions(status: dict[str, Any]) -> list[dict[str, Any]]:
    value = status.get("conditions")
    if not isinstance(value, list):
        return []
    return [item for item in value[:MAX_CONDITIONS] if isinstance(item, dict)]


def _condition_summary(condition: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": _safe_text(condition.get("type"), 120),
        "status": _safe_text(condition.get("status"), 40),
        "reason": _safe_text(condition.get("reason"), 160),
        "message": _safe_text(condition.get("message"), 500),
        "last_transition_time": _safe_text(condition.get("lastTransitionTime"), 80),
    }


def _owner_references(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    rows = []
    for item in value[:MAX_KEYS]:
        if not isinstance(item, dict):
            continue
        rows.append(
            {
                "api_version": _safe_text(item.get("apiVersion"), 80),
                "kind": _safe_text(item.get("kind"), 80),
                "name": _safe_text(item.get("name"), 180),
                "controller": bool(item.get("controller")),
            }
        )
    return rows


def _bounded_keys(value: Any) -> list[str]:
    if not isinstance(value, dict):
        return []
    return sorted(_safe_text(key, 180) for key in value.keys())[:MAX_KEYS]


def _container_count(spec: dict[str, Any]) -> int:
    containers = spec.get("containers")
    if isinstance(containers, list):
        return len(containers)
    pod_spec = _nested(spec, "template.spec")
    containers = pod_spec.get("containers") if isinstance(pod_spec, dict) else []
    return len(containers) if isinstance(containers, list) else 0


def _container_names(spec: dict[str, Any]) -> list[str]:
    containers = spec.get("containers")
    if not isinstance(containers, list):
        pod_spec = _nested(spec, "template.spec")
        containers = pod_spec.get("containers") if isinstance(pod_spec, dict) else []
    return [_safe_text(item.get("name"), 120) for item in containers[:MAX_KEYS] if isinstance(item, dict)]


def _ports(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    rows = []
    for item in value[:MAX_KEYS]:
        if not isinstance(item, dict):
            continue
        rows.append(
            {
                "name": _safe_text(item.get("name"), 80),
                "protocol": _safe_text(item.get("protocol"), 20),
                "port": item.get("port"),
                "target_port": item.get("targetPort"),
            }
        )
    return rows


def _nested(value: dict[str, Any], path: str) -> Any:
    current: Any = value
    for part in path.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


def _required_cluster(cluster_id: str) -> K8sCluster:
    cluster = cluster_for_value(cluster_id)
    if cluster is None:
        raise AdminResourceError("Cluster not found.", code="cluster_not_found", status=404)
    return cluster


def _required_rancher_provider(cluster: K8sCluster) -> K8sProvider:
    provider = cluster.rancher_provider
    if provider is None or not provider.enabled:
        raise AdminResourceError("Enabled Rancher provider is required for live describe.", code="rancher_provider_required", status=409)
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
