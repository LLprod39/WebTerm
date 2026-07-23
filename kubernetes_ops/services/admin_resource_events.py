from __future__ import annotations

import urllib.parse
from typing import Any

from kubernetes_ops.models import K8sAdminAction, K8sCluster, K8sProvider
from kubernetes_ops.services.admin_resources import (
    COMMON_RESOURCES,
    AdminResourceError,
    KubernetesResourceRef,
    active_resource_session_for_user,
    build_resource_ref,
    cluster_for_value,
    rancher_api_path,
    record_admin_resource_action,
    resource_was_redacted,
    sanitize_kubernetes_resource,
)
from kubernetes_ops.services.logs import _redact_log_line
from kubernetes_ops.services.normalizers import payload_items
from kubernetes_ops.services.provider_clients import ProviderJsonClient, ProviderTransport

MAX_RESOURCE_EVENTS = 100


def list_cluster_resource_events(
    *,
    user,
    session_id: str,
    cluster_id: str,
    api_version: str,
    kind: str,
    namespace: str = "",
    name: str = "",
    resource: str = "",
    limit: int | str | None = None,
    transport: ProviderTransport | None = None,
) -> dict[str, Any]:
    cluster = _required_cluster(cluster_id)
    ref = build_resource_ref(api_version=api_version, kind=kind, namespace=namespace, name=name, resource=resource)
    if not ref.name:
        raise AdminResourceError("name is required for resource events.", code="name_required")
    _require_namespace_when_known_namespaced(ref)
    session = active_resource_session_for_user(
        user,
        session_id,
        cluster,
        verb=K8sAdminAction.VERB_LIST,
        namespace=ref.namespace,
        kind=ref.kind,
    )
    provider = _required_rancher_provider(cluster)
    snapshot = fetch_resource_events_snapshot(
        provider=provider, cluster=cluster, ref=ref, limit=limit, transport=transport
    )
    record_admin_resource_action(
        user=user,
        session=session,
        cluster=cluster,
        ref=ref,
        verb=K8sAdminAction.VERB_LIST,
        status=K8sAdminAction.STATUS_COMPLETED,
        response_summary={
            "source": "provider_events",
            "event_count": snapshot["event_count"],
            "truncated": snapshot["truncated"],
            "redacted": snapshot["redacted"],
        },
    )
    return _base_response(
        cluster,
        provider,
        ref,
        path=snapshot["path"],
        limit=snapshot["limit"],
        extra={
            "events": snapshot["events"],
            "event_count": snapshot["event_count"],
            "truncated": snapshot["truncated"],
            "redacted": snapshot["redacted"],
            "source": "provider_events",
        },
    )


def fetch_resource_events_snapshot(
    *,
    provider: K8sProvider,
    cluster: K8sCluster,
    ref: KubernetesResourceRef,
    limit: int | str | None = None,
    transport: ProviderTransport | None = None,
) -> dict[str, Any]:
    event_limit = _bounded_int(limit, default=50, minimum=1, maximum=MAX_RESOURCE_EVENTS)
    path = _resource_events_path(provider, cluster, ref, limit=event_limit)
    try:
        raw = ProviderJsonClient(provider, transport=transport).get(path)
    except Exception as exc:
        raise AdminResourceError(str(exc), code="provider_request_failed", status=502) from exc
    raw_items = payload_items(raw)
    events = [_safe_event(item) for item in raw_items[:event_limit]]
    return {
        "path": path,
        "public_path": _public_path(path),
        "field_selector": _field_selector(ref),
        "limit": event_limit,
        "events": events,
        "event_count": len(events),
        "truncated": len(raw_items) > event_limit,
        "redacted": any(bool(event.get("redacted")) for event in events),
    }


def _base_response(
    cluster: K8sCluster,
    provider: K8sProvider,
    ref: KubernetesResourceRef,
    *,
    path: str,
    limit: int,
    extra: dict[str, Any],
) -> dict[str, Any]:
    return {
        "success": True,
        "mode": "admin_read_only",
        "operation": "resource_events",
        "cluster": {
            "id": f"cluster_{cluster.id}",
            "name": cluster.name,
            "rancher_cluster_id": cluster.rancher_cluster_id,
        },
        "provider": {"id": provider.id, "name": provider.name, "kind": provider.kind},
        "target": {
            "api_version": ref.api_version,
            "kind": ref.kind,
            "resource": ref.resource,
            "namespace": ref.namespace,
            "name": ref.name,
        },
        "path": _public_path(path),
        "field_selector": _field_selector(ref),
        "policy": {
            "mutates_state": False,
            "requires_active_admin_session": True,
            "streaming": False,
            "requested_limit": limit,
            "max_events": MAX_RESOURCE_EVENTS,
            "blocked_actions": ["apply_yaml", "patch", "scale", "delete", "exec", "port_forward", "node_debug"],
        },
        **extra,
    }


def _safe_event(event: dict[str, Any]) -> dict[str, Any]:
    metadata = event.get("metadata") if isinstance(event.get("metadata"), dict) else {}
    involved = event.get("involvedObject") or event.get("regarding") or {}
    source = event.get("source") if isinstance(event.get("source"), dict) else {}
    raw_message = str(event.get("message") or event.get("note") or "")
    message = _safe_text(raw_message, max_length=700)
    involved_object = sanitize_kubernetes_resource(involved if isinstance(involved, dict) else {})
    safe_source = sanitize_kubernetes_resource(source)
    redacted = (
        message != raw_message[:700] or resource_was_redacted(involved_object) or resource_was_redacted(safe_source)
    )
    series = event.get("series") if isinstance(event.get("series"), dict) else {}
    return {
        "name": str(metadata.get("name") or "")[:180],
        "namespace": str(metadata.get("namespace") or "")[:120],
        "type": _safe_text(event.get("type") or event.get("severity") or "", max_length=60),
        "reason": _safe_text(event.get("reason") or "", max_length=160),
        "message": message,
        "source": safe_source,
        "reporting_controller": _safe_text(event.get("reportingController") or "", max_length=180),
        "reporting_instance": _safe_text(event.get("reportingInstance") or "", max_length=180),
        "involved_object": involved_object,
        "count": _safe_int(event.get("count") or event.get("deprecatedCount") or series.get("count")),
        "first_timestamp": str(event.get("firstTimestamp") or event.get("deprecatedFirstTimestamp") or "")[:80],
        "last_timestamp": str(
            event.get("lastTimestamp") or event.get("deprecatedLastTimestamp") or series.get("lastObservedTime") or ""
        )[:80],
        "event_time": str(event.get("eventTime") or "")[:80],
        "resource_version": str(metadata.get("resourceVersion") or "")[:120],
        "redacted": redacted,
    }


def _resource_events_path(provider: K8sProvider, cluster: K8sCluster, ref: KubernetesResourceRef, *, limit: int) -> str:
    base = rancher_api_path(provider, cluster, "v1")
    parts = [base.rstrip("/")]
    if ref.namespace:
        parts.extend(["namespaces", _quote(ref.namespace)])
    parts.append("events")
    params = {"fieldSelector": _field_selector(ref), "limit": str(limit)}
    return "/".join(parts) + "?" + urllib.parse.urlencode(params)


def _field_selector(ref: KubernetesResourceRef) -> str:
    parts = [
        f"involvedObject.apiVersion={ref.api_version}",
        f"involvedObject.kind={ref.kind}",
        f"involvedObject.name={ref.name}",
    ]
    if ref.namespace:
        parts.append(f"involvedObject.namespace={ref.namespace}")
    return ",".join(parts)


def _require_namespace_when_known_namespaced(ref: KubernetesResourceRef) -> None:
    configured = COMMON_RESOURCES.get((ref.api_version, ref.kind))
    if configured and configured.get("namespaced") and not ref.namespace:
        raise AdminResourceError("namespace is required for namespaced resource events.", code="namespace_required")


def _required_cluster(cluster_id: str) -> K8sCluster:
    cluster = cluster_for_value(cluster_id)
    if cluster is None:
        raise AdminResourceError("Cluster not found.", code="cluster_not_found", status=404)
    return cluster


def _required_rancher_provider(cluster: K8sCluster) -> K8sProvider:
    provider = cluster.rancher_provider
    if provider is None or not provider.enabled:
        raise AdminResourceError(
            "Enabled Rancher provider is required for resource events.", code="rancher_provider_required", status=409
        )
    return provider


def _safe_text(value: object, *, max_length: int) -> str:
    return _redact_log_line(str(value or "").replace("\r", ""))[:max_length]


def _safe_int(value: object) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return 0
    return parsed if parsed >= 0 else 0


def _bounded_int(value: int | str | None, *, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value) if value is not None else default
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(parsed, maximum))


def _quote(value: str) -> str:
    return urllib.parse.quote(str(value), safe="")


def _public_path(path: str) -> str:
    parsed = urllib.parse.urlsplit(str(path or ""))
    return urllib.parse.urlunsplit(("", "", parsed.path or "/", "", ""))[:500]
