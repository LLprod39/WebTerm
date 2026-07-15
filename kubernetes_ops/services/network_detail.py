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
MAX_RELATED_WORKLOADS = 20
MAX_RELATED_PODS = 50
MAX_RELATED_NETWORK = 20
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
ENDPOINT_NAME_KEYS = (
    "app",
    "backend",
    "backendServiceName",
    "name",
    "pod",
    "podName",
    "resourceName",
    "service",
    "serviceName",
    "target",
    "workload",
)
BLOCKED_ACTIONS = ("exec", "port_forward", "delete", "service_edit", "ingress_edit", "patch", "apply_yaml")
REQUESTABLE_ACTIONS = ("logs.snapshot", "diagnosis.create_draft", "approval.request")


def network_for_value(network_id: str) -> K8sNetworkRef | None:
    value = str(network_id or "").strip()
    prefix, _, numeric = value.partition("_")
    rows = K8sNetworkRef.objects.select_related("cluster")
    if prefix == "network" and numeric.isdigit():
        return rows.filter(id=int(numeric)).first()
    if value.isdigit():
        return rows.filter(id=int(value)).first()
    return None


def build_network_detail(item: K8sNetworkRef, *, user=None) -> dict[str, Any]:
    owner_apps = _owner_apps(item)
    workloads = _related_workloads(item, owner_apps=owner_apps)
    pods = _related_pods(item, owner_apps=owner_apps, workloads=workloads)
    related_network = _related_network(item)
    events = _related_events(item)
    return {
        "success": True,
        "mode": "read_only",
        "operation": "network_detail",
        "source": "normalized_inventory",
        "cluster": _safe_payload(serialize_cluster(item.cluster, user=user)),
        "network_ref": _safe_payload(serialize_network_ref(item, user=user)),
        "owner_apps": [_safe_payload(serialize_app(app, user=user)) for app in owner_apps],
        "workloads": [_safe_payload(serialize_workload(workload, user=user)) for workload in workloads],
        "pods": [_safe_payload(serialize_pod_ref(pod, user=user)) for pod in pods],
        "related_network_refs": [_safe_payload(serialize_network_ref(ref, user=user)) for ref in related_network],
        "events": [_safe_payload(_event_payload(event)) for event in events],
        "summary": _summary(
            item,
            owner_apps=owner_apps,
            workloads=workloads,
            pods=pods,
            related_network=related_network,
            events=events,
        ),
        "policy": {
            "mode": "read_only",
            "mutates_state": False,
            "source": "normalized_inventory",
            "external_ui": "staff_admin_fallback",
            "blocked_actions": list(BLOCKED_ACTIONS),
            "requestable_actions": list(REQUESTABLE_ACTIONS),
        },
    }


def network_detail_audit_payload(payload: dict[str, Any]) -> dict[str, Any]:
    cluster = payload.get("cluster") if isinstance(payload.get("cluster"), dict) else {}
    network = payload.get("network_ref") if isinstance(payload.get("network_ref"), dict) else {}
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    return {
        "cluster_id": str(cluster.get("id") or ""),
        "cluster_name": str(cluster.get("name") or ""),
        "network_id": str(network.get("id") or ""),
        "network_name": str(network.get("name") or ""),
        "network_kind": str(network.get("kind") or ""),
        "namespace": str(network.get("namespace") or ""),
        "owner_app_count": int(summary.get("owner_app_count") or 0),
        "workload_count": int(summary.get("workload_count") or 0),
        "pod_count": int(summary.get("pod_count") or 0),
        "related_network_count": int(summary.get("related_network_count") or 0),
        "event_count": int(summary.get("event_count") or 0),
    }


def _owner_apps(item: K8sNetworkRef) -> list[K8sAppRef]:
    values = _match_values(item)
    rows = K8sAppRef.objects.filter(cluster=item.cluster, namespace=item.namespace).select_related("cluster").order_by("owner", "name")[:100]
    matched: list[K8sAppRef] = []
    for app in rows:
        if _name_matches(app.name, values) or _labels_match(app.labels, values):
            matched.append(app)
    return matched[:MAX_OWNER_APPS]


def _related_workloads(item: K8sNetworkRef, *, owner_apps: list[K8sAppRef]) -> list[K8sWorkloadRef]:
    values = _match_values(item)
    values.update(app.name for app in owner_apps)
    rows = K8sWorkloadRef.objects.filter(cluster=item.cluster, namespace=item.namespace).select_related("cluster").order_by("kind", "name")[:150]
    matched: list[K8sWorkloadRef] = []
    for workload in rows:
        if _name_matches(workload.name, values) or _labels_match(workload.labels, values):
            matched.append(workload)
    return matched[:MAX_RELATED_WORKLOADS]


def _related_pods(item: K8sNetworkRef, *, owner_apps: list[K8sAppRef], workloads: list[K8sWorkloadRef]) -> list[K8sPodRef]:
    values = _match_values(item)
    values.update(app.name for app in owner_apps)
    values.update(workload.name for workload in workloads)
    rows = K8sPodRef.objects.filter(cluster=item.cluster, namespace=item.namespace).select_related("cluster").order_by("name")[:200]
    matched: list[K8sPodRef] = []
    endpoint_text = _payload_text([item.endpoints, item.hosts, item.ports])
    for pod in rows:
        if (
            _name_matches(pod.name, values)
            or _name_matches(pod.owner_name, values)
            or _labels_match(pod.labels, values)
            or (pod.name and pod.name in endpoint_text)
            or (pod.pod_ip and pod.pod_ip in endpoint_text)
        ):
            matched.append(pod)
    return matched[:MAX_RELATED_PODS]


def _related_network(item: K8sNetworkRef) -> list[K8sNetworkRef]:
    values = _match_values(item)
    rows = (
        K8sNetworkRef.objects.filter(cluster=item.cluster, namespace=item.namespace)
        .exclude(id=item.id)
        .select_related("cluster")
        .order_by("kind", "name")[:100]
    )
    matched: list[K8sNetworkRef] = []
    for candidate in rows:
        candidate_text = _payload_text([candidate.endpoints, candidate.hosts, candidate.ports])
        item_text = _payload_text([item.endpoints, item.hosts, item.ports])
        if (
            _name_matches(candidate.name, values)
            or _labels_match(candidate.labels, values)
            or (item.name and item.name in candidate_text)
            or (candidate.name and candidate.name in item_text)
        ):
            matched.append(candidate)
    return matched[:MAX_RELATED_NETWORK]


def _related_events(item: K8sNetworkRef) -> list[K8sEvent | K8sAuditEvent]:
    kind_values = {"Service"} if item.kind == K8sNetworkRef.KIND_SERVICE else {"Ingress"}
    native_events = list(
        K8sEvent.objects.filter(cluster=item.cluster, namespace=item.namespace)
        .filter(Q(involved_name=item.name) | Q(message__icontains=item.name) | Q(involved_kind__in=kind_values, involved_name=item.name))
        .order_by("-last_seen_at", "-id")[:MAX_RELATED_EVENTS]
    )
    if native_events:
        return native_events
    audit_events = (
        K8sAuditEvent.objects.filter(cluster=item.cluster)
        .filter(
            Q(payload__network_id=f"network_{item.id}")
            | Q(payload__network_id=item.id)
            | Q(payload__network_name=item.name)
            | Q(payload__target_name=item.name)
            | Q(payload__target__network=item.name)
            | Q(payload__target__name=item.name)
        )
        .select_related("user", "cluster")
        .order_by("-created_at", "-id")[:MAX_RELATED_EVENTS]
    )
    return list(audit_events)


def _summary(
    item: K8sNetworkRef,
    *,
    owner_apps: list[K8sAppRef],
    workloads: list[K8sWorkloadRef],
    pods: list[K8sPodRef],
    related_network: list[K8sNetworkRef],
    events: list[K8sEvent | K8sAuditEvent],
) -> dict[str, Any]:
    warning_events = [event for event in events if isinstance(event, K8sEvent) and event.severity in {K8sEvent.SEVERITY_WARNING, K8sEvent.SEVERITY_ERROR}]
    return {
        "health": item.health,
        "kind": item.kind,
        "namespace": item.namespace,
        "service_type": item.service_type,
        "port_count": len(item.ports or []),
        "host_count": len(item.hosts or []),
        "endpoint_count": len(item.endpoints or []),
        "owner_app_count": len(owner_apps),
        "workload_count": len(workloads),
        "pod_count": len(pods),
        "related_network_count": len(related_network),
        "event_count": len(events),
        "warning_event_count": len(warning_events),
        "ready_containers": sum(pod.ready_containers for pod in pods),
        "total_containers": sum(pod.total_containers for pod in pods),
        "restart_count": sum(pod.restart_count for pod in pods),
        "owners": sorted({item for item in [*(app.owner for app in owner_apps), *(workload.owner for workload in workloads)] if item}),
        "teams": sorted({item for item in [*(app.team for app in owner_apps), *(workload.team for workload in workloads)] if item}),
        "workload_kinds": _counts_by(workloads, "kind"),
    }


def _match_values(item: K8sNetworkRef) -> set[str]:
    values = {item.name}
    if isinstance(item.labels, dict):
        for key in APP_LABEL_KEYS:
            value = str(item.labels.get(key) or "").strip()
            if value:
                values.add(value)
    values.update(_endpoint_values(item.endpoints))
    return {str(value or "").strip() for value in values if str(value or "").strip()}


def _endpoint_values(value: Any) -> set[str]:
    values: set[str] = set()
    if isinstance(value, dict):
        for key, nested in value.items():
            if key in ENDPOINT_NAME_KEYS:
                text = str(nested or "").strip()
                if text:
                    values.add(text)
            values.update(_endpoint_values(nested))
    elif isinstance(value, list):
        for item in value:
            values.update(_endpoint_values(item))
    return values


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


def _payload_text(value: Any) -> str:
    if isinstance(value, (dict, list, tuple)):
        return " ".join(_payload_text(item) for item in (value.values() if isinstance(value, dict) else value))
    return str(value or "")


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
