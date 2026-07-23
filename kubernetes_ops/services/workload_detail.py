from __future__ import annotations

from typing import Any

from django.db.models import Q

from kubernetes_ops.models import (
    K8sAppRef,
    K8sAuditEvent,
    K8sCluster,
    K8sEvent,
    K8sNetworkRef,
    K8sPodRef,
    K8sWorkloadRef,
)
from kubernetes_ops.serializers import (
    serialize_app,
    serialize_cluster,
    serialize_cluster_event,
    serialize_kubernetes_event,
    serialize_network_ref,
    serialize_pod_ref,
    serialize_workload,
)
from kubernetes_ops.services.logs import _redact_log_line

MAX_OWNER_APPS = 10
MAX_RELATED_PODS = 120
MAX_RELATED_NETWORK = 80
MAX_RELATED_EVENTS = 60
MAX_TEXT_LENGTH = 1_000
SENSITIVE_KEY_PARTS = ("token", "secret", "password", "credential", "kubeconfig", "authorization", "api_key", "apikey")
APP_LABEL_KEYS = (
    "app",
    "app.kubernetes.io/name",
    "app.kubernetes.io/instance",
    "devtron.ai/app",
    "devtron.ai/app-name",
    "devtron.ai/application",
)
BLOCKED_ACTIONS = ("exec", "port_forward", "delete", "scale", "rollout_restart", "patch", "apply_yaml")
REQUESTABLE_ACTIONS = ("logs.snapshot", "diagnosis.create_draft", "approval.request", "gitops.create_merge_request")


def workload_for_value(workload_id: str) -> K8sWorkloadRef | None:
    value = str(workload_id or "").strip()
    prefix, _, numeric = value.partition("_")
    rows = K8sWorkloadRef.objects.select_related("cluster")
    if prefix == "workload" and numeric.isdigit():
        return rows.filter(id=int(numeric)).first()
    if value.isdigit():
        return rows.filter(id=int(value)).first()
    return None


def build_workload_detail(workload: K8sWorkloadRef, *, user=None) -> dict[str, Any]:
    owner_apps = _owner_apps(workload)
    pods = _related_pods(workload, owner_apps=owner_apps)
    network_refs = _related_network(workload, owner_apps=owner_apps)
    events = _related_events(workload, pods=pods)
    return {
        "success": True,
        "mode": "read_only",
        "operation": "workload_detail",
        "source": "normalized_inventory",
        "cluster": _safe_payload(serialize_cluster(workload.cluster, user=user)),
        "workload": _safe_payload(serialize_workload(workload, user=user)),
        "owner_apps": [_safe_payload(serialize_app(app, user=user)) for app in owner_apps],
        "pods": [_safe_payload(serialize_pod_ref(pod, user=user)) for pod in pods],
        "network_refs": [_safe_payload(serialize_network_ref(item, user=user)) for item in network_refs],
        "events": [_safe_payload(_event_payload(event)) for event in events],
        "summary": _summary(workload, owner_apps=owner_apps, pods=pods, network_refs=network_refs, events=events),
        "policy": {
            "mode": "read_only",
            "mutates_state": False,
            "source": "normalized_inventory",
            "external_ui": "staff_admin_fallback",
            "blocked_actions": list(BLOCKED_ACTIONS),
            "requestable_actions": list(REQUESTABLE_ACTIONS),
        },
    }


def workload_detail_audit_payload(payload: dict[str, Any]) -> dict[str, Any]:
    cluster = payload.get("cluster") if isinstance(payload.get("cluster"), dict) else {}
    workload = payload.get("workload") if isinstance(payload.get("workload"), dict) else {}
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    return {
        "cluster_id": str(cluster.get("id") or ""),
        "cluster_name": str(cluster.get("name") or ""),
        "workload_id": str(workload.get("id") or ""),
        "workload_name": str(workload.get("name") or ""),
        "namespace": str(workload.get("namespace") or ""),
        "kind": str(workload.get("kind") or ""),
        "owner_app_count": int(summary.get("owner_app_count") or 0),
        "pod_count": int(summary.get("pod_count") or 0),
        "network_count": int(summary.get("network_count") or 0),
        "event_count": int(summary.get("event_count") or 0),
    }


def _owner_apps(workload: K8sWorkloadRef) -> list[K8sAppRef]:
    values = _match_values(workload.name, workload.labels)
    rows = (
        K8sAppRef.objects.filter(cluster=workload.cluster, namespace=workload.namespace)
        .select_related("cluster")
        .order_by("owner", "name")[:100]
    )
    matched: list[K8sAppRef] = []
    for app in rows:
        if (
            _name_matches(app.name, values)
            or _labels_match(app.labels, values)
            or workload.name.startswith(f"{app.name}-")
        ):
            matched.append(app)
    return matched[:MAX_OWNER_APPS]


def _related_pods(workload: K8sWorkloadRef, *, owner_apps: list[K8sAppRef]) -> list[K8sPodRef]:
    values = _match_values(workload.name, workload.labels)
    values.update(app.name for app in owner_apps)
    rows = (
        K8sPodRef.objects.filter(cluster=workload.cluster, namespace=workload.namespace)
        .select_related("cluster")
        .order_by("name")[:250]
    )
    matched: list[K8sPodRef] = []
    for pod in rows:
        if (
            _name_matches(pod.owner_name, values)
            or _name_matches(pod.name, values)
            or _labels_match(pod.labels, values)
        ):
            matched.append(pod)
    return matched[:MAX_RELATED_PODS]


def _related_network(workload: K8sWorkloadRef, *, owner_apps: list[K8sAppRef]) -> list[K8sNetworkRef]:
    values = _match_values(workload.name, workload.labels)
    values.update(app.name for app in owner_apps)
    rows = (
        K8sNetworkRef.objects.filter(cluster=workload.cluster, namespace=workload.namespace)
        .select_related("cluster")
        .order_by("kind", "name")[:120]
    )
    matched: list[K8sNetworkRef] = []
    for item in rows:
        if _name_matches(item.name, values) or _labels_match(item.labels, values):
            matched.append(item)
    return matched[:MAX_RELATED_NETWORK]


def _related_events(workload: K8sWorkloadRef, *, pods: list[K8sPodRef]) -> list[K8sEvent | K8sAuditEvent]:
    pod_names = {pod.name for pod in pods}
    native_events = list(
        K8sEvent.objects.filter(cluster=workload.cluster, namespace=workload.namespace)
        .filter(Q(involved_name=workload.name) | Q(message__icontains=workload.name) | Q(involved_name__in=pod_names))
        .order_by("-last_seen_at", "-id")[:MAX_RELATED_EVENTS]
    )
    if native_events:
        return native_events
    audit_events = (
        K8sAuditEvent.objects.filter(cluster=workload.cluster)
        .filter(
            Q(payload__workload_id=f"workload_{workload.id}")
            | Q(payload__workload_id=workload.id)
            | Q(payload__workload_name=workload.name)
            | Q(payload__target_name=workload.name)
            | Q(payload__target__workload=workload.name)
            | Q(payload__target__name=workload.name)
        )
        .select_related("user", "cluster")
        .order_by("-created_at", "-id")[:MAX_RELATED_EVENTS]
    )
    return list(audit_events)


def _summary(
    workload: K8sWorkloadRef,
    *,
    owner_apps: list[K8sAppRef],
    pods: list[K8sPodRef],
    network_refs: list[K8sNetworkRef],
    events: list[K8sEvent | K8sAuditEvent],
) -> dict[str, Any]:
    warning_events = [
        event
        for event in events
        if isinstance(event, K8sEvent) and event.severity in {K8sEvent.SEVERITY_WARNING, K8sEvent.SEVERITY_ERROR}
    ]
    return {
        "health": workload.health,
        "namespace": workload.namespace,
        "kind": workload.kind,
        "owner": workload.owner,
        "team": workload.team,
        "version": workload.version,
        "ready": workload.ready,
        "desired": workload.desired,
        "owner_app_count": len(owner_apps),
        "pod_count": len(pods),
        "network_count": len(network_refs),
        "event_count": len(events),
        "warning_event_count": len(warning_events),
        "unhealthy_pod_count": sum(1 for pod in pods if pod.health != K8sCluster.HEALTH_HEALTHY),
        "ready_containers": sum(pod.ready_containers for pod in pods),
        "total_containers": sum(pod.total_containers for pod in pods),
        "restart_count": sum(pod.restart_count for pod in pods),
        "owners": sorted({item for item in [workload.owner, *(app.owner for app in owner_apps)] if item}),
        "teams": sorted({item for item in [workload.team, *(app.team for app in owner_apps)] if item}),
        "versions": sorted({item for item in [workload.version, *(app.version for app in owner_apps)] if item}),
    }


def _match_values(name: str, labels: Any) -> set[str]:
    values = {str(name or "").strip()}
    if isinstance(labels, dict):
        for key in APP_LABEL_KEYS:
            value = str(labels.get(key) or "").strip()
            if value:
                values.add(value)
    return {value for value in values if value}


def _name_matches(name: str, values: set[str]) -> bool:
    normalized = str(name or "").strip().lower()
    if not normalized:
        return False
    for value in values:
        candidate = str(value or "").strip().lower()
        if normalized == candidate or normalized.startswith(f"{candidate}-") or candidate.startswith(f"{normalized}-"):
            return True
    return False


def _labels_match(labels: Any, values: set[str]) -> bool:
    if not isinstance(labels, dict):
        return False
    normalized_values = {value.lower() for value in values}
    for key in APP_LABEL_KEYS:
        value = str(labels.get(key) or "").strip().lower()
        if value and value in normalized_values:
            return True
    return False


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
