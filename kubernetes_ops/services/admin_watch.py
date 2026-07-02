from __future__ import annotations

import urllib.parse
from typing import Any

from kubernetes_ops.models import K8sAdminAction, K8sCluster, K8sProvider
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
from kubernetes_ops.services.provider_clients import KubernetesProviderError, ProviderJsonClient, ProviderTransport

MAX_WATCH_EVENTS = 50
MAX_TIMEOUT_SECONDS = 30


def get_admin_resource_watch_preview(
    *,
    user,
    session_id: str,
    cluster_id: str,
    api_version: str,
    kind: str,
    namespace: str = "",
    name: str = "",
    resource: str = "",
    resource_version: str = "",
    limit: int | str | None = None,
    timeout_seconds: int | str | None = None,
    transport: ProviderTransport | None = None,
    streaming: bool = False,
) -> dict[str, Any]:
    cluster = _required_cluster(cluster_id)
    ref = build_resource_ref(api_version=api_version, kind=kind, namespace=namespace, name=name, resource=resource)
    session = active_resource_session_for_user(user, session_id, cluster, verb=K8sAdminAction.VERB_WATCH, namespace=ref.namespace, kind=ref.kind)
    provider = _required_rancher_provider(cluster)
    event_limit = _bounded_int(limit, default=20, minimum=1, maximum=MAX_WATCH_EVENTS)
    timeout = _bounded_int(timeout_seconds, default=10, minimum=1, maximum=MAX_TIMEOUT_SECONDS)
    resource_version_value = str(resource_version or "").strip()[:120]
    base_path = rancher_resource_path(provider, cluster, ref)
    path = _watch_path(base_path, resource_version=resource_version_value, timeout_seconds=timeout)
    payload = _base_response(cluster, provider, ref, path=path, limit=event_limit, timeout_seconds=timeout, resource_version=resource_version_value, streaming=streaming)

    try:
        raw = ProviderJsonClient(provider, transport=transport, timeout=timeout + 5).get(path)
        events, truncated, observed_resource_version = _normalize_watch_payload(raw, event_limit)
    except (KubernetesProviderError, ValueError, KeyError) as exc:
        payload["source"] = "provider_error"
        payload["message"] = str(exc)
        _record_watch_action(user=user, session=session, cluster=cluster, ref=ref, payload=payload)
        return payload

    latest_resource_version = observed_resource_version or resource_version_value
    payload.update(
        {
            "available": True,
            "source": "provider_watch_stream_batch" if streaming else "provider_watch_preview",
            "events": events,
            "event_count": len(events),
            "truncated": truncated,
            "latest_resource_version": latest_resource_version,
            "message": "",
        }
    )
    _record_watch_action(user=user, session=session, cluster=cluster, ref=ref, payload=payload)
    return payload


def get_admin_resource_watch_stream_batch(
    *,
    user,
    session_id: str,
    cluster_id: str,
    api_version: str,
    kind: str,
    namespace: str = "",
    name: str = "",
    resource: str = "",
    resource_version: str = "",
    limit: int | str | None = None,
    timeout_seconds: int | str | None = None,
    transport: ProviderTransport | None = None,
) -> dict[str, Any]:
    return get_admin_resource_watch_preview(
        user=user,
        session_id=session_id,
        cluster_id=cluster_id,
        api_version=api_version,
        kind=kind,
        namespace=namespace,
        name=name,
        resource=resource,
        resource_version=resource_version,
        limit=limit,
        timeout_seconds=timeout_seconds,
        transport=transport,
        streaming=True,
    )


def prepare_admin_resource_watch_continuous_stream(
    *,
    user,
    session_id: str,
    cluster_id: str,
    api_version: str,
    kind: str,
    namespace: str = "",
    name: str = "",
    resource: str = "",
    resource_version: str = "",
    limit: int | str | None = None,
    timeout_seconds: int | str | None = None,
) -> dict[str, Any]:
    cluster = _required_cluster(cluster_id)
    ref = build_resource_ref(api_version=api_version, kind=kind, namespace=namespace, name=name, resource=resource)
    active_resource_session_for_user(user, session_id, cluster, verb=K8sAdminAction.VERB_WATCH, namespace=ref.namespace, kind=ref.kind)
    provider = _required_rancher_provider(cluster)
    event_limit = _bounded_int(limit, default=20, minimum=1, maximum=MAX_WATCH_EVENTS)
    timeout = _bounded_int(timeout_seconds, default=10, minimum=1, maximum=MAX_TIMEOUT_SECONDS)
    resource_version_value = str(resource_version or "").strip()[:120]
    path = _watch_path(rancher_resource_path(provider, cluster, ref), resource_version=resource_version_value, timeout_seconds=timeout)
    payload = _base_response(cluster, provider, ref, path=path, limit=event_limit, timeout_seconds=timeout, resource_version=resource_version_value, streaming=True)
    payload.update({"operation": "resource_watch_stream_continuous", "source": "provider_watch_stream_continuous"})
    payload["policy"].update({"stream_transport": "provider_native_continuous"})
    return {"provider": provider, "path": path, "timeout_seconds": timeout, "event_limit": event_limit, "payload": payload}


def build_admin_resource_watch_continuous_payload(
    context: dict[str, Any],
    *,
    raw_events: list[dict[str, Any]],
    provider_truncated: bool,
    eof: bool,
    event_limit: int | str,
) -> dict[str, Any]:
    payload = dict(context["payload"])
    payload["policy"] = dict(payload.get("policy") or {})
    limit = _bounded_int(event_limit, default=context["event_limit"], minimum=1, maximum=MAX_WATCH_EVENTS)
    events, normalized_truncated, observed_resource_version = _normalize_watch_payload({"items": raw_events}, limit)
    latest_resource_version = observed_resource_version or str(payload.get("latest_resource_version") or "")
    payload.update(
        {
            "available": True,
            "source": "provider_watch_stream_continuous",
            "events": events,
            "event_count": len(events),
            "truncated": bool(provider_truncated or normalized_truncated),
            "latest_resource_version": latest_resource_version,
            "stream_eof": bool(eof),
            "message": "",
        }
    )
    return payload


def _normalize_watch_payload(payload: dict[str, Any], limit: int) -> tuple[list[dict[str, Any]], bool, str]:
    raw_events = _event_items(payload)
    events: list[dict[str, Any]] = []
    truncated = False
    latest_delivered_resource_version = ""
    latest_bookmark_resource_version = ""
    for raw_event in raw_events:
        if not isinstance(raw_event, dict):
            continue
        event_type = _watch_event_type(raw_event)
        obj = _watch_event_object(raw_event)
        if event_type == "BOOKMARK":
            latest_bookmark_resource_version = _resource_version_from_object(obj) or latest_bookmark_resource_version
            continue
        if len(events) >= limit:
            truncated = True
            continue
        sanitized = sanitize_kubernetes_resource(obj)
        resource_version = _resource_version_from_object(sanitized)
        latest_delivered_resource_version = resource_version or latest_delivered_resource_version
        events.append(
            {
                "type": event_type,
                "object": sanitized,
                "resource_version": resource_version,
                "redacted": resource_was_redacted(sanitized),
            }
        )
    if truncated:
        return events, True, latest_delivered_resource_version
    return events, False, latest_bookmark_resource_version or latest_delivered_resource_version


def _event_items(payload: dict[str, Any]) -> list[Any]:
    for key in ("events", "items", "data"):
        value = payload.get(key)
        if isinstance(value, list):
            return value
    if isinstance(payload.get("object"), dict) or payload.get("type"):
        return [payload]
    return []


def _watch_event_type(raw_event: dict[str, Any]) -> str:
    return str(raw_event.get("type") or raw_event.get("event_type") or "SNAPSHOT").strip()[:40].upper() or "SNAPSHOT"


def _watch_event_object(raw_event: dict[str, Any]) -> Any:
    return raw_event.get("object") if "object" in raw_event else raw_event.get("resource", raw_event)


def _base_response(
    cluster: K8sCluster,
    provider: K8sProvider,
    ref: KubernetesResourceRef,
    *,
    path: str,
    limit: int,
    timeout_seconds: int,
    resource_version: str,
    streaming: bool,
) -> dict[str, Any]:
    source = "provider_watch_stream_batch" if streaming else "provider_watch_preview"
    return {
        "success": True,
        "mode": "admin_read_only",
        "operation": "resource_watch_stream_batch" if streaming else "resource_watch_preview",
        "cluster": {"id": f"cluster_{cluster.id}", "name": cluster.name, "rancher_cluster_id": cluster.rancher_cluster_id},
        "provider": {"id": provider.id, "name": provider.name, "kind": provider.kind},
        "target": {
            "api_version": ref.api_version,
            "kind": ref.kind,
            "resource": ref.resource,
            "namespace": ref.namespace,
            "name": ref.name,
        },
        "path": _public_path(path),
        "available": False,
        "source": source,
        "events": [],
        "event_count": 0,
        "truncated": False,
        "latest_resource_version": resource_version,
        "message": "",
        "policy": {
            "mutates_state": False,
            "requires_active_admin_session": True,
            "streaming": bool(streaming),
            "future_stream_transport": "websocket_or_sse",
            "max_events": MAX_WATCH_EVENTS,
            "requested_limit": limit,
            "timeout_seconds": timeout_seconds,
            "blocked_actions": ["apply_yaml", "patch", "scale", "delete", "exec", "port_forward", "node_debug"],
        },
    }


def _record_watch_action(*, user, session, cluster: K8sCluster, ref: KubernetesResourceRef, payload: dict[str, Any]) -> None:
    record_admin_resource_action(
        user=user,
        session=session,
        cluster=cluster,
        ref=ref,
        verb=K8sAdminAction.VERB_WATCH,
        status=K8sAdminAction.STATUS_COMPLETED,
        response_summary={
            "source": payload.get("source", ""),
            "available": bool(payload.get("available")),
            "event_count": payload.get("event_count", 0),
            "truncated": bool(payload.get("truncated")),
            "latest_resource_version": payload.get("latest_resource_version", ""),
        },
    )


def _watch_path(path: str, *, resource_version: str, timeout_seconds: int) -> str:
    separator = "&" if "?" in path else "?"
    params = {"watch": "1", "allowWatchBookmarks": "true", "timeoutSeconds": str(timeout_seconds)}
    if resource_version:
        params["resourceVersion"] = resource_version
    return f"{path}{separator}{urllib.parse.urlencode(params)}"


def _bounded_int(value: int | str | None, *, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value) if value is not None else default
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(parsed, maximum))


def _resource_version_from_object(value: Any) -> str:
    metadata = value.get("metadata") if isinstance(value, dict) else {}
    if isinstance(metadata, dict):
        return str(metadata.get("resourceVersion") or "")
    return ""


def _required_cluster(cluster_id: str) -> K8sCluster:
    cluster = cluster_for_value(cluster_id)
    if cluster is None:
        raise AdminResourceError("Cluster not found.", code="cluster_not_found", status=404)
    return cluster


def _required_rancher_provider(cluster: K8sCluster) -> K8sProvider:
    provider = cluster.rancher_provider
    if provider is None or not provider.enabled:
        raise AdminResourceError("Enabled Rancher provider is required for Admin Mode resource watch.", code="rancher_provider_required", status=409)
    return provider


def _public_path(path: str) -> str:
    parsed = urllib.parse.urlsplit(str(path or ""))
    return urllib.parse.urlunsplit(("", "", parsed.path or "/", "", ""))[:500]
