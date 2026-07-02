from __future__ import annotations

from typing import Any

from django.db.models import Q

from kubernetes_ops.models import K8sAppRef, K8sAuditEvent, K8sCluster, K8sEvent, K8sNetworkRef, K8sPodRef, K8sWorkloadRef
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


MAX_OWNER_WORKLOADS = 10
MAX_OWNER_APPS = 10
MAX_SIBLING_PODS = 30
MAX_RELATED_NETWORK = 30
MAX_RELATED_EVENTS = 40
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
BLOCKED_ACTIONS = ("exec", "attach", "port_forward", "delete", "restart", "scale", "patch", "apply_yaml")
REQUESTABLE_ACTIONS = ("logs.snapshot", "diagnosis.create_draft", "approval.request")


def pod_for_value(pod_id: str) -> K8sPodRef | None:
    value = str(pod_id or "").strip()
    prefix, _, numeric = value.partition("_")
    rows = K8sPodRef.objects.select_related("cluster")
    if prefix == "pod" and numeric.isdigit():
        return rows.filter(id=int(numeric)).first()
    if value.isdigit():
        return rows.filter(id=int(value)).first()
    return None


def build_pod_detail(pod: K8sPodRef, *, user=None) -> dict[str, Any]:
    owner_workloads = _owner_workloads(pod)
    owner_apps = _owner_apps(pod, owner_workloads)
    sibling_pods = _sibling_pods(pod, owner_workloads=owner_workloads, owner_apps=owner_apps)
    network_refs = _related_network(pod, owner_workloads=owner_workloads, owner_apps=owner_apps)
    events = _related_events(pod)
    return {
        "success": True,
        "mode": "read_only",
        "operation": "pod_detail",
        "source": "normalized_inventory",
        "cluster": _safe_payload(serialize_cluster(pod.cluster, user=user)),
        "pod": _safe_payload(serialize_pod_ref(pod, user=user)),
        "owner_workloads": [_safe_payload(serialize_workload(workload, user=user)) for workload in owner_workloads],
        "owner_apps": [_safe_payload(serialize_app(app, user=user)) for app in owner_apps],
        "sibling_pods": [_safe_payload(serialize_pod_ref(item, user=user)) for item in sibling_pods],
        "network_refs": [_safe_payload(serialize_network_ref(item, user=user)) for item in network_refs],
        "events": [_safe_payload(_event_payload(event)) for event in events],
        "summary": _summary(pod, owner_workloads=owner_workloads, owner_apps=owner_apps, sibling_pods=sibling_pods, network_refs=network_refs, events=events),
        "policy": {
            "mode": "read_only",
            "mutates_state": False,
            "source": "normalized_inventory",
            "logs": {
                "snapshot_endpoint": f"/api/kubernetes/pods/pod_{pod.id}/logs/",
                "streaming": False,
            },
            "external_ui": "staff_admin_fallback",
            "blocked_actions": list(BLOCKED_ACTIONS),
            "requestable_actions": list(REQUESTABLE_ACTIONS),
        },
    }


def pod_detail_audit_payload(payload: dict[str, Any]) -> dict[str, Any]:
    cluster = payload.get("cluster") if isinstance(payload.get("cluster"), dict) else {}
    pod = payload.get("pod") if isinstance(payload.get("pod"), dict) else {}
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    return {
        "cluster_id": str(cluster.get("id") or ""),
        "cluster_name": str(cluster.get("name") or ""),
        "pod_id": str(pod.get("id") or ""),
        "pod_name": str(pod.get("name") or ""),
        "namespace": str(pod.get("namespace") or ""),
        "owner_workload_count": int(summary.get("owner_workload_count") or 0),
        "owner_app_count": int(summary.get("owner_app_count") or 0),
        "sibling_pod_count": int(summary.get("sibling_pod_count") or 0),
        "network_count": int(summary.get("network_count") or 0),
        "event_count": int(summary.get("event_count") or 0),
    }


def _owner_workloads(pod: K8sPodRef) -> list[K8sWorkloadRef]:
    values = _match_values(pod)
    rows = K8sWorkloadRef.objects.filter(cluster=pod.cluster, namespace=pod.namespace).select_related("cluster").order_by("kind", "name")[:100]
    matched: list[K8sWorkloadRef] = []
    for workload in rows:
        if _name_matches(workload.name, values) or _labels_match(workload.labels, values) or pod.name.startswith(f"{workload.name}-"):
            matched.append(workload)
    return matched[:MAX_OWNER_WORKLOADS]


def _owner_apps(pod: K8sPodRef, owner_workloads: list[K8sWorkloadRef]) -> list[K8sAppRef]:
    values = _match_values(pod)
    values.update(workload.name for workload in owner_workloads)
    rows = K8sAppRef.objects.filter(cluster=pod.cluster, namespace=pod.namespace).select_related("cluster").order_by("owner", "name")[:100]
    matched: list[K8sAppRef] = []
    for app in rows:
        if _name_matches(app.name, values) or _labels_match(app.labels, values) or pod.name.startswith(f"{app.name}-"):
            matched.append(app)
    return matched[:MAX_OWNER_APPS]


def _sibling_pods(pod: K8sPodRef, *, owner_workloads: list[K8sWorkloadRef], owner_apps: list[K8sAppRef]) -> list[K8sPodRef]:
    values = _match_values(pod)
    values.update(workload.name for workload in owner_workloads)
    values.update(app.name for app in owner_apps)
    rows = K8sPodRef.objects.filter(cluster=pod.cluster, namespace=pod.namespace).exclude(id=pod.id).select_related("cluster").order_by("name")[:200]
    matched: list[K8sPodRef] = []
    for item in rows:
        if _name_matches(item.owner_name, values) or _name_matches(item.name, values) or _labels_match(item.labels, values):
            matched.append(item)
    return matched[:MAX_SIBLING_PODS]


def _related_network(pod: K8sPodRef, *, owner_workloads: list[K8sWorkloadRef], owner_apps: list[K8sAppRef]) -> list[K8sNetworkRef]:
    values = _match_values(pod)
    values.update(workload.name for workload in owner_workloads)
    values.update(app.name for app in owner_apps)
    rows = K8sNetworkRef.objects.filter(cluster=pod.cluster, namespace=pod.namespace).select_related("cluster").order_by("kind", "name")[:100]
    matched: list[K8sNetworkRef] = []
    for item in rows:
        if _name_matches(item.name, values) or _labels_match(item.labels, values) or _network_targets_pod(item, pod):
            matched.append(item)
    return matched[:MAX_RELATED_NETWORK]


def _related_events(pod: K8sPodRef) -> list[K8sEvent | K8sAuditEvent]:
    native_events = list(
        K8sEvent.objects.filter(cluster=pod.cluster, namespace=pod.namespace)
        .filter(Q(involved_name=pod.name) | Q(message__icontains=pod.name))
        .order_by("-last_seen_at", "-id")[:MAX_RELATED_EVENTS]
    )
    if native_events:
        return native_events
    audit_events = (
        K8sAuditEvent.objects.filter(cluster=pod.cluster)
        .filter(
            Q(payload__pod_id=f"pod_{pod.id}")
            | Q(payload__pod_id=pod.id)
            | Q(payload__pod_name=pod.name)
            | Q(payload__target_name=pod.name)
            | Q(payload__target__pod=pod.name)
            | Q(payload__target__name=pod.name)
        )
        .select_related("user", "cluster")
        .order_by("-created_at", "-id")[:MAX_RELATED_EVENTS]
    )
    return list(audit_events)


def _summary(
    pod: K8sPodRef,
    *,
    owner_workloads: list[K8sWorkloadRef],
    owner_apps: list[K8sAppRef],
    sibling_pods: list[K8sPodRef],
    network_refs: list[K8sNetworkRef],
    events: list[K8sEvent | K8sAuditEvent],
) -> dict[str, Any]:
    warning_events = [event for event in events if isinstance(event, K8sEvent) and event.severity in {K8sEvent.SEVERITY_WARNING, K8sEvent.SEVERITY_ERROR}]
    related_pods = [pod, *sibling_pods]
    return {
        "health": pod.health,
        "phase": pod.phase,
        "namespace": pod.namespace,
        "node_name": pod.node_name,
        "owner_kind": pod.owner_kind,
        "owner_name": pod.owner_name,
        "ready_containers": pod.ready_containers,
        "total_containers": pod.total_containers,
        "restart_count": pod.restart_count,
        "owner_workload_count": len(owner_workloads),
        "owner_app_count": len(owner_apps),
        "sibling_pod_count": len(sibling_pods),
        "network_count": len(network_refs),
        "event_count": len(events),
        "warning_event_count": len(warning_events),
        "related_ready_containers": sum(item.ready_containers for item in related_pods),
        "related_total_containers": sum(item.total_containers for item in related_pods),
        "related_restart_count": sum(item.restart_count for item in related_pods),
        "images": _safe_payload(pod.images or []),
        "owners": sorted({item for item in [*(app.owner for app in owner_apps), *(workload.owner for workload in owner_workloads)] if item}),
        "teams": sorted({item for item in [*(app.team for app in owner_apps), *(workload.team for workload in owner_workloads)] if item}),
    }


def _match_values(pod: K8sPodRef) -> set[str]:
    values = {pod.name, pod.owner_name, *_owner_name_candidates(pod.owner_name)}
    if isinstance(pod.labels, dict):
        for key in APP_LABEL_KEYS:
            value = str(pod.labels.get(key) or "").strip()
            if value:
                values.add(value)
    return {str(value or "").strip() for value in values if str(value or "").strip()}


def _owner_name_candidates(owner_name: str) -> set[str]:
    text = str(owner_name or "").strip()
    if not text or "-" not in text:
        return set()
    return {text.rsplit("-", 1)[0]}


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


def _network_targets_pod(item: K8sNetworkRef, pod: K8sPodRef) -> bool:
    text = str(item.endpoints or "")
    if pod.name and pod.name in text:
        return True
    return bool(pod.pod_ip and pod.pod_ip in text)


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
        return [_safe_payload(item, depth=depth + 1) for item in value[:MAX_SIBLING_PODS]]
    if isinstance(value, str):
        redacted = _redact_log_line(value)
        if len(redacted) > MAX_TEXT_LENGTH:
            return f"{redacted[:MAX_TEXT_LENGTH]}...[truncated]"
        return redacted
    return value


def _is_sensitive_key(key: str) -> bool:
    normalized = str(key or "").replace("-", "_").lower()
    return any(part in normalized for part in SENSITIVE_KEY_PARTS)
