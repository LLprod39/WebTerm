from __future__ import annotations

import urllib.parse
from typing import Any

from kubernetes_ops.models import K8sAdminAction, K8sCluster, K8sProvider
from kubernetes_ops.services.admin_resources import (
    AdminResourceError,
    KubernetesResourceRef,
    active_resource_session_for_user,
    cluster_for_value,
    record_admin_resource_action,
)
from kubernetes_ops.services.logs import (
    BLOCKED_ACTIONS,
    MAX_TAIL_LINES,
    _default_pod_logs_path_template,
    _normalize_log_payload,
    _tail_limit,
)
from kubernetes_ops.services.provider_clients import (
    KubernetesProviderError,
    ProviderJsonClient,
    ProviderTransport,
    provider_path,
)

MAX_LOG_STREAM_TIMEOUT_SECONDS = 30


def get_admin_pod_log_snapshot(
    *,
    user,
    session_id: str,
    cluster_id: str,
    namespace: str,
    pod_name: str,
    tail_lines: int | str | None = None,
    container: str = "",
    transport: ProviderTransport | None = None,
) -> dict[str, Any]:
    cluster = _required_cluster(cluster_id)
    namespace_value = str(namespace or "").strip()
    pod_value = str(pod_name or "").strip()
    container_value = str(container or "").strip()
    if not namespace_value:
        raise AdminResourceError("namespace is required for pod logs.", code="namespace_required")
    if not pod_value:
        raise AdminResourceError("pod name is required for pod logs.", code="pod_name_required")

    session = active_resource_session_for_user(
        user,
        session_id,
        cluster,
        verb=K8sAdminAction.VERB_LOGS,
        namespace=namespace_value,
        kind="Pod",
    )
    provider = _required_rancher_provider(cluster)
    tail = _tail_limit(tail_lines)
    template = provider_path(provider, "pod_logs_path_template", "").strip() or _default_pod_logs_path_template(
        provider
    )
    ref = KubernetesResourceRef(
        api_version="v1", kind="Pod", resource="pods", namespace=namespace_value, name=pod_value
    )
    payload = _base_response(cluster, provider, ref, tail=tail, container=container_value)

    if not template:
        payload["source"] = "not_configured"
        payload["message"] = "Provider pod_logs_path_template is not configured."
        _record_log_action(user=user, session=session, cluster=cluster, ref=ref, payload=payload)
        return payload

    path = _format_log_path(
        template, cluster=cluster, namespace=namespace_value, pod_name=pod_value, tail=tail, container=container_value
    )
    payload["path"] = _public_path(path)
    try:
        raw = ProviderJsonClient(provider, transport=transport).get_log_payload(path)
        lines, truncated = _normalize_log_payload(raw, tail)
    except (KubernetesProviderError, ValueError, KeyError) as exc:
        payload["source"] = "provider_error"
        payload["message"] = str(exc)
        _record_log_action(user=user, session=session, cluster=cluster, ref=ref, payload=payload)
        return payload

    payload.update(
        {
            "available": True,
            "source": "provider_snapshot",
            "lines": lines,
            "line_count": len(lines),
            "truncated": truncated,
            "message": "",
        }
    )
    _record_log_action(user=user, session=session, cluster=cluster, ref=ref, payload=payload)
    return payload


def get_admin_pod_log_stream_batch(
    *,
    user,
    session_id: str,
    cluster_id: str,
    namespace: str,
    pod_name: str,
    tail_lines: int | str | None = None,
    container: str = "",
    timeout_seconds: int | str | None = None,
    transport: ProviderTransport | None = None,
) -> dict[str, Any]:
    cluster = _required_cluster(cluster_id)
    namespace_value = str(namespace or "").strip()
    pod_value = str(pod_name or "").strip()
    container_value = str(container or "").strip()
    if not namespace_value:
        raise AdminResourceError("namespace is required for pod logs.", code="namespace_required")
    if not pod_value:
        raise AdminResourceError("pod name is required for pod logs.", code="pod_name_required")

    session = active_resource_session_for_user(
        user,
        session_id,
        cluster,
        verb=K8sAdminAction.VERB_LOGS,
        namespace=namespace_value,
        kind="Pod",
    )
    provider = _required_rancher_provider(cluster)
    tail = _tail_limit(tail_lines)
    timeout = _stream_timeout(timeout_seconds)
    template = provider_path(provider, "pod_logs_stream_path_template", "").strip()
    ref = KubernetesResourceRef(
        api_version="v1", kind="Pod", resource="pods", namespace=namespace_value, name=pod_value
    )
    payload = _base_response(cluster, provider, ref, tail=tail, container=container_value)
    payload["policy"]["streaming"] = True
    payload["policy"]["timeout_seconds"] = timeout

    if not template:
        return get_admin_pod_log_snapshot(
            user=user,
            session_id=session_id,
            cluster_id=cluster_id,
            namespace=namespace_value,
            pod_name=pod_value,
            tail_lines=tail,
            container=container_value,
            transport=transport,
        )

    path = _format_log_path(
        template, cluster=cluster, namespace=namespace_value, pod_name=pod_value, tail=tail, container=container_value
    )
    payload["path"] = _public_path(path)
    try:
        raw_lines, provider_truncated = ProviderJsonClient(
            provider, transport=transport, timeout=timeout
        ).stream_log_lines(path, max_lines=tail)
        lines, normalized_truncated = _normalize_log_payload({"lines": raw_lines}, tail)
    except (KubernetesProviderError, ValueError, KeyError) as exc:
        payload["source"] = "provider_stream_error"
        payload["message"] = str(exc)
        _record_log_action(user=user, session=session, cluster=cluster, ref=ref, payload=payload)
        return payload

    payload.update(
        {
            "available": True,
            "source": "provider_stream_batch",
            "lines": lines,
            "line_count": len(lines),
            "truncated": bool(provider_truncated or normalized_truncated),
            "message": "",
        }
    )
    _record_log_action(user=user, session=session, cluster=cluster, ref=ref, payload=payload)
    return payload


def prepare_admin_pod_log_continuous_stream(
    *,
    user,
    session_id: str,
    cluster_id: str,
    namespace: str,
    pod_name: str,
    tail_lines: int | str | None = None,
    container: str = "",
    timeout_seconds: int | str | None = None,
) -> dict[str, Any]:
    cluster = _required_cluster(cluster_id)
    namespace_value = str(namespace or "").strip()
    pod_value = str(pod_name or "").strip()
    container_value = str(container or "").strip()
    if not namespace_value:
        raise AdminResourceError("namespace is required for pod logs.", code="namespace_required")
    if not pod_value:
        raise AdminResourceError("pod name is required for pod logs.", code="pod_name_required")

    active_resource_session_for_user(
        user,
        session_id,
        cluster,
        verb=K8sAdminAction.VERB_LOGS,
        namespace=namespace_value,
        kind="Pod",
    )
    provider = _required_rancher_provider(cluster)
    tail = _tail_limit(tail_lines)
    timeout = _stream_timeout(timeout_seconds)
    template = provider_path(provider, "pod_logs_stream_path_template", "").strip()
    if not template:
        raise AdminResourceError(
            "Provider pod_logs_stream_path_template is required for continuous pod logs.",
            code="pod_log_stream_template_required",
            status=409,
        )

    ref = KubernetesResourceRef(
        api_version="v1", kind="Pod", resource="pods", namespace=namespace_value, name=pod_value
    )
    path = _format_log_path(
        template, cluster=cluster, namespace=namespace_value, pod_name=pod_value, tail=tail, container=container_value
    )
    payload = _base_response(cluster, provider, ref, tail=tail, container=container_value)
    payload.update(
        {"operation": "pod_logs_stream_continuous", "source": "provider_stream_continuous", "path": _public_path(path)}
    )
    payload["policy"].update(
        {"streaming": True, "stream_transport": "provider_native_continuous", "timeout_seconds": timeout}
    )
    return {"provider": provider, "path": path, "timeout_seconds": timeout, "tail_lines": tail, "payload": payload}


def build_admin_pod_log_continuous_payload(
    context: dict[str, Any],
    *,
    raw_lines: list[str],
    provider_truncated: bool,
    eof: bool,
    line_limit: int | str,
) -> dict[str, Any]:
    payload = dict(context["payload"])
    payload["policy"] = dict(payload.get("policy") or {})
    limit = _tail_limit(line_limit)
    lines, normalized_truncated = _normalize_log_payload({"lines": raw_lines}, limit)
    payload.update(
        {
            "available": True,
            "source": "provider_stream_continuous",
            "lines": lines,
            "line_count": len(lines),
            "truncated": bool(provider_truncated or normalized_truncated),
            "stream_eof": bool(eof),
            "message": "",
        }
    )
    return payload


def _base_response(
    cluster: K8sCluster,
    provider: K8sProvider,
    ref: KubernetesResourceRef,
    *,
    tail: int,
    container: str,
) -> dict[str, Any]:
    return {
        "success": True,
        "mode": "admin_read_only",
        "operation": "pod_logs_snapshot",
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
            "container": container,
        },
        "path": "",
        "available": False,
        "source": "not_configured",
        "lines": [],
        "line_count": 0,
        "truncated": False,
        "message": "",
        "policy": {
            "mutates_state": False,
            "requires_active_admin_session": True,
            "streaming": False,
            "source": "rancher_provider_json",
            "requested_tail_lines": tail,
            "max_tail_lines": MAX_TAIL_LINES,
            "blocked_actions": list(BLOCKED_ACTIONS),
        },
    }


def _record_log_action(
    *, user, session, cluster: K8sCluster, ref: KubernetesResourceRef, payload: dict[str, Any]
) -> None:
    record_admin_resource_action(
        user=user,
        session=session,
        cluster=cluster,
        ref=ref,
        verb=K8sAdminAction.VERB_LOGS,
        status=K8sAdminAction.STATUS_COMPLETED,
        response_summary={
            "source": payload.get("source", ""),
            "available": bool(payload.get("available")),
            "line_count": payload.get("line_count", 0),
            "tail_lines": payload.get("policy", {}).get("requested_tail_lines"),
            "truncated": bool(payload.get("truncated")),
            "container_present": bool(payload.get("target", {}).get("container")),
        },
    )


def _required_cluster(cluster_id: str) -> K8sCluster:
    cluster = cluster_for_value(cluster_id)
    if cluster is None:
        raise AdminResourceError("Cluster not found.", code="cluster_not_found", status=404)
    return cluster


def _required_rancher_provider(cluster: K8sCluster) -> K8sProvider:
    provider = cluster.rancher_provider
    if provider is None or not provider.enabled:
        raise AdminResourceError(
            "Enabled Rancher provider is required for Admin Mode pod logs.",
            code="rancher_provider_required",
            status=409,
        )
    return provider


def _format_log_path(
    template: str, *, cluster: K8sCluster, namespace: str, pod_name: str, tail: int, container: str
) -> str:
    values = {
        "cluster_id": _quote(cluster.rancher_cluster_id or str(cluster.id)),
        "cluster_name": _quote(cluster.name),
        "namespace": _quote(namespace),
        "pod_name": _quote(pod_name),
        "tail": str(tail),
        "container": _quote(container),
    }
    path = template.format(**values)
    return _append_container_query(path, template=template, container=container)


def _append_container_query(path: str, *, template: str, container: str) -> str:
    container_value = str(container or "").strip()
    if not container_value or "{container}" in str(template or ""):
        return path
    parsed = urllib.parse.urlsplit(path)
    query_items = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
    if any(key == "container" for key, _value in query_items):
        return path
    separator = "&" if parsed.query else "?"
    return f"{path}{separator}container={_quote(container_value)}"


def _quote(value: str) -> str:
    return urllib.parse.quote(str(value), safe="")


def _public_path(path: str) -> str:
    parsed = urllib.parse.urlsplit(str(path or ""))
    return urllib.parse.urlunsplit(("", "", parsed.path or "/", "", ""))[:500]


def _stream_timeout(value: int | str | None) -> int:
    try:
        parsed = int(value) if value is not None else 10
    except (TypeError, ValueError):
        parsed = 10
    return max(1, min(parsed, MAX_LOG_STREAM_TIMEOUT_SECONDS))
