from __future__ import annotations

from typing import Any

from django.db.models import Q

from kubernetes_ops.models import (
    K8sAppRef,
    K8sAuditEvent,
    K8sCluster,
    K8sEvent,
    K8sNamespace,
    K8sNetworkRef,
    K8sPodRef,
    K8sWorkloadRef,
)
from kubernetes_ops.serializers import (
    serialize_app,
    serialize_cluster,
    serialize_cluster_event,
    serialize_kubernetes_event,
    serialize_namespace,
    serialize_network_ref,
    serialize_pod_ref,
    serialize_workload,
)
from kubernetes_ops.services.logs import _redact_log_line

MAX_RELATED_APPS = 50
MAX_RELATED_WORKLOADS = 100
MAX_RELATED_PODS = 150
MAX_RELATED_NETWORK = 100
MAX_RELATED_EVENTS = 80
MAX_TEXT_LENGTH = 1_000
SENSITIVE_KEY_PARTS = ("token", "secret", "password", "credential", "kubeconfig", "authorization", "api_key", "apikey")
BLOCKED_ACTIONS = (
    "exec",
    "port_forward",
    "terminal",
    "node_debug",
    "delete",
    "scale",
    "rollout_restart",
    "patch",
    "apply_yaml",
)
REQUESTABLE_ACTIONS = ("diagnosis.create_draft", "gitops.create_merge_request", "approval.request")


def namespace_for_value(cluster: K8sCluster, namespace_id: str) -> K8sNamespace | None:
    value = str(namespace_id or "").strip()
    prefix, _, numeric = value.partition("_")
    rows = K8sNamespace.objects.select_related("cluster").filter(cluster=cluster)
    if prefix == "namespace" and numeric.isdigit():
        return rows.filter(id=int(numeric)).first()
    if value.isdigit():
        return rows.filter(id=int(value)).first()
    return rows.filter(name=value).first()


def build_namespace_detail(cluster: K8sCluster, namespace_id: str, *, user=None) -> dict[str, Any] | None:
    namespace = namespace_for_value(cluster, namespace_id)
    namespace_name = namespace.name if namespace is not None else _fallback_namespace_name(cluster, namespace_id)
    if not namespace_name:
        return None
    apps = list(
        K8sAppRef.objects.filter(cluster=cluster, namespace=namespace_name)
        .select_related("cluster")
        .order_by("owner", "name")[:MAX_RELATED_APPS]
    )
    workloads = list(
        K8sWorkloadRef.objects.filter(cluster=cluster, namespace=namespace_name)
        .select_related("cluster")
        .order_by("kind", "name")[:MAX_RELATED_WORKLOADS]
    )
    pods = list(
        K8sPodRef.objects.filter(cluster=cluster, namespace=namespace_name)
        .select_related("cluster")
        .order_by("name")[:MAX_RELATED_PODS]
    )
    network = list(
        K8sNetworkRef.objects.filter(cluster=cluster, namespace=namespace_name)
        .select_related("cluster")
        .order_by("kind", "name")[:MAX_RELATED_NETWORK]
    )
    events = _related_events(cluster, namespace_name)
    return {
        "success": True,
        "mode": "read_only",
        "operation": "namespace_detail",
        "source": "normalized_inventory",
        "cluster": _safe_payload(serialize_cluster(cluster, user=user)),
        "namespace": _namespace_payload(
            cluster, namespace_name, namespace=namespace, user=user, apps=apps, workloads=workloads
        ),
        "apps": [_safe_payload(serialize_app(app, user=user)) for app in apps],
        "workloads": [_safe_payload(serialize_workload(workload, user=user)) for workload in workloads],
        "pods": [_safe_payload(serialize_pod_ref(pod, user=user)) for pod in pods],
        "network_refs": [_safe_payload(serialize_network_ref(item, user=user)) for item in network],
        "events": [_safe_payload(_event_payload(event)) for event in events],
        "summary": _summary(namespace_name, apps=apps, workloads=workloads, pods=pods, network=network, events=events),
        "policy": {
            "mode": "read_only",
            "mutates_state": False,
            "source": "normalized_inventory",
            "external_ui": "staff_admin_fallback",
            "blocked_actions": list(BLOCKED_ACTIONS),
            "requestable_actions": list(REQUESTABLE_ACTIONS),
        },
    }


def namespace_detail_audit_payload(payload: dict[str, Any]) -> dict[str, Any]:
    cluster = payload.get("cluster") if isinstance(payload.get("cluster"), dict) else {}
    namespace = payload.get("namespace") if isinstance(payload.get("namespace"), dict) else {}
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    return {
        "cluster_id": str(cluster.get("id") or ""),
        "cluster_name": str(cluster.get("name") or ""),
        "namespace_id": str(namespace.get("id") or ""),
        "namespace": str(namespace.get("name") or ""),
        "app_count": int(summary.get("app_count") or 0),
        "workload_count": int(summary.get("workload_count") or 0),
        "pod_count": int(summary.get("pod_count") or 0),
        "network_count": int(summary.get("network_count") or 0),
        "event_count": int(summary.get("event_count") or 0),
    }


def _fallback_namespace_name(cluster: K8sCluster, namespace_id: str) -> str:
    value = str(namespace_id or "").strip()
    prefix, _, numeric = value.partition("_")
    if not value or (prefix == "namespace" and numeric.isdigit()) or value.isdigit():
        return ""
    if _namespace_has_rows(cluster, value):
        return value
    return ""


def _namespace_has_rows(cluster: K8sCluster, name: str) -> bool:
    filters = {"cluster": cluster, "namespace": name}
    return (
        K8sAppRef.objects.filter(**filters).exists()
        or K8sWorkloadRef.objects.filter(**filters).exists()
        or K8sPodRef.objects.filter(**filters).exists()
        or K8sNetworkRef.objects.filter(**filters).exists()
        or K8sEvent.objects.filter(**filters).exists()
    )


def _namespace_payload(
    cluster: K8sCluster,
    namespace_name: str,
    *,
    namespace: K8sNamespace | None,
    user=None,
    apps: list[K8sAppRef],
    workloads: list[K8sWorkloadRef],
) -> dict[str, Any]:
    if namespace is not None:
        return _safe_payload(serialize_namespace(namespace, user=user))
    owners = sorted(
        {item for item in [*(app.owner for app in apps), *(workload.owner for workload in workloads)] if item}
    )
    teams = sorted({item for item in [*(app.team for app in apps), *(workload.team for workload in workloads)] if item})
    health = _aggregate_health([*(app.health for app in apps), *(workload.health for workload in workloads)])
    external_links_visible = bool(getattr(user, "is_staff", False))
    return {
        "id": f"{cluster.id}:{namespace_name}",
        "database_id": None,
        "name": namespace_name,
        "cluster_id": f"cluster_{cluster.id}",
        "cluster_name": cluster.name,
        "environment": cluster.environment,
        "health": health,
        "apps": len(apps),
        "workloads": len(workloads),
        "owners": owners,
        "teams": teams,
        "links": {},
        "external_links_policy": {
            "visible": external_links_visible,
            "mode": "staff_admin_fallback" if external_links_visible else "webterm_native_only",
            "reason": ""
            if external_links_visible
            else "External Rancher/Fleet/Devtron UI links are staff/admin fallback only.",
        },
        "labels": {},
    }


def _related_events(cluster: K8sCluster, namespace_name: str) -> list[K8sEvent | K8sAuditEvent]:
    native_events = list(
        K8sEvent.objects.filter(cluster=cluster, namespace=namespace_name).order_by("-last_seen_at", "-id")[
            :MAX_RELATED_EVENTS
        ]
    )
    if native_events:
        return native_events
    audit_events = (
        K8sAuditEvent.objects.filter(cluster=cluster)
        .filter(
            Q(payload__namespace=namespace_name)
            | Q(payload__namespace_name=namespace_name)
            | Q(payload__target_namespace=namespace_name)
            | Q(payload__target__namespace=namespace_name)
        )
        .select_related("user", "cluster")
        .order_by("-created_at", "-id")[:MAX_RELATED_EVENTS]
    )
    return list(audit_events)


def _summary(
    namespace_name: str,
    *,
    apps: list[K8sAppRef],
    workloads: list[K8sWorkloadRef],
    pods: list[K8sPodRef],
    network: list[K8sNetworkRef],
    events: list[K8sEvent | K8sAuditEvent],
) -> dict[str, Any]:
    warning_events = [
        event
        for event in events
        if isinstance(event, K8sEvent) and event.severity in {K8sEvent.SEVERITY_WARNING, K8sEvent.SEVERITY_ERROR}
    ]
    return {
        "namespace": namespace_name,
        "health": _aggregate_health(
            [*(app.health for app in apps), *(workload.health for workload in workloads), *(pod.health for pod in pods)]
        ),
        "app_count": len(apps),
        "workload_count": len(workloads),
        "pod_count": len(pods),
        "network_count": len(network),
        "event_count": len(events),
        "warning_event_count": len(warning_events),
        "unhealthy_app_count": sum(1 for app in apps if app.health != K8sCluster.HEALTH_HEALTHY),
        "unhealthy_workload_count": sum(1 for workload in workloads if workload.health != K8sCluster.HEALTH_HEALTHY),
        "unhealthy_pod_count": sum(1 for pod in pods if pod.health != K8sCluster.HEALTH_HEALTHY),
        "ready_workloads": sum(1 for workload in workloads if workload.desired and workload.ready >= workload.desired),
        "desired_workloads": len(workloads),
        "ready_containers": sum(pod.ready_containers for pod in pods),
        "total_containers": sum(pod.total_containers for pod in pods),
        "restart_count": sum(pod.restart_count for pod in pods),
        "owners": sorted(
            {item for item in [*(app.owner for app in apps), *(workload.owner for workload in workloads)] if item}
        ),
        "teams": sorted(
            {item for item in [*(app.team for app in apps), *(workload.team for workload in workloads)] if item}
        ),
        "workload_kinds": _counts_by(workloads, "kind"),
        "network_kinds": _counts_by(network, "kind"),
    }


def _aggregate_health(values: list[str]) -> str:
    healths = {value for value in values if value}
    if K8sCluster.HEALTH_DEGRADED in healths:
        return K8sCluster.HEALTH_DEGRADED
    if K8sCluster.HEALTH_WARNING in healths:
        return K8sCluster.HEALTH_WARNING
    if K8sCluster.HEALTH_HEALTHY in healths:
        return K8sCluster.HEALTH_HEALTHY
    return K8sCluster.HEALTH_UNKNOWN


def _counts_by(rows: list[Any], attr: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        key = str(getattr(row, attr, "") or "unknown")
        counts[key] = counts.get(key, 0) + 1
    return counts


def _event_payload(event: K8sEvent | K8sAuditEvent) -> dict[str, Any]:
    if isinstance(event, K8sEvent):
        return serialize_kubernetes_event(event)
    return serialize_cluster_event(event)


def _safe_payload(value: Any, *, depth: int = 0) -> Any:
    if depth > 6:
        return "[truncated]"
    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}
        for raw_key, raw_value in value.items():
            key = str(raw_key)
            if _is_sensitive_key(key):
                sanitized[key] = "[redacted]"
            else:
                sanitized[key] = _safe_payload(raw_value, depth=depth + 1)
        return sanitized
    if isinstance(value, list):
        return [_safe_payload(item, depth=depth + 1) for item in value[:MAX_RELATED_PODS]]
    if isinstance(value, str):
        redacted = _redact_log_line(value)
        if len(redacted) > MAX_TEXT_LENGTH:
            return f"{redacted[:MAX_TEXT_LENGTH]}...[truncated]"
        return redacted
    return value


def _is_sensitive_key(key: str) -> bool:
    normalized = str(key or "").replace("-", "_").lower()
    return any(part in normalized for part in SENSITIVE_KEY_PARTS)
