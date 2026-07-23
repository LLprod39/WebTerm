from __future__ import annotations

from typing import Any

from django.db.models import Q

from kubernetes_ops.models import K8sAppRef, K8sAuditEvent, K8sCluster, K8sEvent, K8sPodRef, K8sWorkloadRef
from kubernetes_ops.serializers import (
    serialize_app,
    serialize_cluster,
    serialize_cluster_event,
    serialize_kubernetes_event,
    serialize_pod_ref,
    serialize_workload,
)
from kubernetes_ops.services.logs import _redact_log_line

MAX_RELATED_WORKLOADS = 25
MAX_RELATED_PODS = 50
MAX_RELATED_EVENTS = 40
MAX_TEXT_LENGTH = 1_000
SENSITIVE_KEY_PARTS = ("token", "secret", "password", "credential", "kubeconfig", "authorization", "api_key", "apikey")
DEVTRON_FLOW_LINKS = ("logs", "history", "values", "rollback", "devtron_app")
APP_LABEL_KEYS = (
    "app",
    "app.kubernetes.io/name",
    "app.kubernetes.io/instance",
    "devtron.ai/app",
    "devtron.ai/app-name",
    "devtron.ai/application",
)
BLOCKED_ACTIONS = ("exec", "port_forward", "delete", "scale", "rollout_restart", "apply_yaml", "devtron_rollback")


def devtron_app_for_value(app_id: str) -> K8sAppRef | None:
    value = str(app_id or "").strip()
    prefix, _, numeric = value.partition("_")
    if prefix == "app" and numeric.isdigit():
        return _devtron_apps().filter(id=int(numeric)).first()
    if value.isdigit():
        return _devtron_apps().filter(id=int(value)).first()
    return None


def build_devtron_app_detail(app: K8sAppRef, *, user=None) -> dict[str, Any]:
    workloads = _related_workloads(app)
    pods = _related_pods(app, workloads)
    events = _related_events(app, workloads, pods)
    app_payload = _safe_payload(serialize_app(app, user=user))
    workload_payloads = [_safe_payload(serialize_workload(workload, user=user)) for workload in workloads]
    pod_payloads = [_safe_payload(serialize_pod_ref(pod, user=user)) for pod in pods]
    event_payloads = [_safe_payload(_event_payload(event)) for event in events]
    delivery_context = _delivery_context(app, app_payload=app_payload, workloads=workloads, pods=pods)
    return {
        "success": True,
        "mode": "read_only",
        "operation": "devtron_app_detail",
        "source": "normalized_inventory",
        "app": app_payload,
        "cluster": _safe_payload(serialize_cluster(app.cluster, user=user)),
        "workloads": workload_payloads,
        "pods": pod_payloads,
        "events": event_payloads,
        "delivery_context": delivery_context,
        "summary": _summary(app, workloads=workloads, pods=pods, events=events, delivery_context=delivery_context),
        "policy": {
            "mode": "read_only",
            "mutates_state": False,
            "source": "normalized_inventory",
            "external_ui": "staff_admin_fallback",
            "change_path": "devtron_rollback_or_deploy",
            "blocked_actions": list(BLOCKED_ACTIONS),
            "requestable_actions": ["devtron.open_rollback", "actions.diagnose"],
        },
    }


def devtron_app_audit_payload(payload: dict[str, Any]) -> dict[str, Any]:
    app = payload.get("app") if isinstance(payload.get("app"), dict) else {}
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    delivery = payload.get("delivery_context") if isinstance(payload.get("delivery_context"), dict) else {}
    return {
        "app_id": str(app.get("id") or ""),
        "app_name": str(app.get("name") or ""),
        "namespace": str(app.get("namespace") or ""),
        "workload_count": int(summary.get("workload_count") or 0),
        "pod_count": int(summary.get("pod_count") or 0),
        "event_count": int(summary.get("event_count") or 0),
        "delivery_capabilities": list(delivery.get("capabilities") or [])[:10],
        "values_visible": bool((delivery.get("values") or {}).get("visible"))
        if isinstance(delivery.get("values"), dict)
        else False,
    }


def _devtron_apps():
    return K8sAppRef.objects.select_related("cluster").filter(owner=K8sAppRef.OWNER_DEVTRON)


def _related_workloads(app: K8sAppRef) -> list[K8sWorkloadRef]:
    values = _match_values(app.name, app.labels)
    candidates = (
        K8sWorkloadRef.objects.filter(cluster=app.cluster, namespace=app.namespace)
        .select_related("cluster")
        .order_by("kind", "name")[:100]
    )
    rows = [
        workload
        for workload in candidates
        if _name_matches(workload.name, values) or _labels_match(workload.labels, values)
    ]
    return rows[:MAX_RELATED_WORKLOADS]


def _related_pods(app: K8sAppRef, workloads: list[K8sWorkloadRef]) -> list[K8sPodRef]:
    values = _match_values(app.name, app.labels)
    workload_names = {workload.name for workload in workloads}
    candidates = (
        K8sPodRef.objects.filter(cluster=app.cluster, namespace=app.namespace)
        .select_related("cluster")
        .order_by("name")[:200]
    )
    rows = []
    for pod in candidates:
        owner_name = str(pod.owner_name or "")
        if (
            _name_matches(pod.name, values)
            or owner_name in workload_names
            or any(_name_matches(pod.name, {name}) for name in workload_names)
            or _labels_match(pod.labels, values)
        ):
            rows.append(pod)
    return rows[:MAX_RELATED_PODS]


def _related_events(
    app: K8sAppRef, workloads: list[K8sWorkloadRef], pods: list[K8sPodRef]
) -> list[K8sEvent | K8sAuditEvent]:
    names = {app.name, *(workload.name for workload in workloads), *(pod.name for pod in pods)}
    names = {name for name in names if name}
    query = Q(involved_name__in=names)
    if app.name:
        query |= Q(message__icontains=app.name)
    native_events = list(
        K8sEvent.objects.filter(cluster=app.cluster, namespace=app.namespace)
        .filter(query)
        .order_by("-last_seen_at", "-id")[:MAX_RELATED_EVENTS]
    )
    if native_events:
        return native_events
    audit_events = (
        K8sAuditEvent.objects.filter(cluster=app.cluster)
        .filter(
            Q(payload__app_id=f"app_{app.id}")
            | Q(payload__app_id=app.id)
            | Q(payload__app_name=app.name)
            | Q(payload__target_name=app.name)
        )
        .select_related("user", "cluster")
        .order_by("-created_at", "-id")[:MAX_RELATED_EVENTS]
    )
    return list(audit_events)


def _summary(
    app: K8sAppRef,
    *,
    workloads: list[K8sWorkloadRef],
    pods: list[K8sPodRef],
    events: list[K8sEvent | K8sAuditEvent],
    delivery_context: dict[str, Any],
) -> dict[str, Any]:
    warning_events = [
        event
        for event in events
        if isinstance(event, K8sEvent) and event.severity in {K8sEvent.SEVERITY_WARNING, K8sEvent.SEVERITY_ERROR}
    ]
    return {
        "health": app.health,
        "version": app.version,
        "workload_count": len(workloads),
        "pod_count": len(pods),
        "event_count": len(events),
        "warning_event_count": len(warning_events),
        "unhealthy_workload_count": sum(1 for workload in workloads if workload.health != K8sCluster.HEALTH_HEALTHY),
        "unhealthy_pod_count": sum(1 for pod in pods if pod.health != K8sCluster.HEALTH_HEALTHY),
        "ready_workloads": sum(1 for workload in workloads if workload.desired and workload.ready >= workload.desired),
        "desired_workloads": len(workloads),
        "ready_containers": sum(pod.ready_containers for pod in pods),
        "total_containers": sum(pod.total_containers for pod in pods),
        "restart_count": sum(pod.restart_count for pod in pods),
        "teams": sorted({item for item in [app.team, *(workload.team for workload in workloads)] if item}),
        "versions": sorted({item for item in [app.version, *(workload.version for workload in workloads)] if item}),
        "delivery_capabilities": list(delivery_context.get("capabilities") or []),
        "rollback_context_available": bool((delivery_context.get("rollback") or {}).get("available")),
        "history_context_available": bool((delivery_context.get("history") or {}).get("available")),
        "values_context_available": bool((delivery_context.get("values") or {}).get("available")),
    }


def _delivery_context(
    app: K8sAppRef, *, app_payload: dict[str, Any], workloads: list[K8sWorkloadRef], pods: list[K8sPodRef]
) -> dict[str, Any]:
    labels = app.labels if isinstance(app.labels, dict) else {}
    visible_links = app_payload.get("links") if isinstance(app_payload.get("links"), dict) else {}
    flow_links = {key: visible_links.get(key) for key in DEVTRON_FLOW_LINKS if visible_links.get(key)}
    values_preview = _values_preview(labels)
    capabilities = []
    if flow_links.get("history") or _label_value(labels, "devtron.ai/deployment-id", "deployment_id", "deploymentId"):
        capabilities.append("deployment_history")
    if flow_links.get("values") or values_preview["available"]:
        capabilities.append("helm_values")
    if flow_links.get("rollback") or app.version:
        capabilities.append("rollback_context")
    if flow_links.get("logs") or pods:
        capabilities.append("logs")
    return {
        "source": "normalized_inventory",
        "owner": K8sAppRef.OWNER_DEVTRON,
        "chart": {
            "name": _label_value(labels, "helm.sh/chart", "chart", "chartName", "devtron.ai/chart") or app.version,
            "version": _label_value(labels, "app.kubernetes.io/version", "chartVersion", "devtron.ai/chart-version")
            or app.version,
            "release": _label_value(labels, "meta.helm.sh/release-name", "app.kubernetes.io/instance", "release")
            or app.name,
        },
        "history": {
            "available": "deployment_history" in capabilities,
            "latest_version": app.version,
            "link": flow_links.get("history", ""),
            "evidence": _history_evidence(labels),
        },
        "values": values_preview,
        "rollback": {
            "available": "rollback_context" in capabilities,
            "link": flow_links.get("rollback", ""),
            "strategy": "devtron_previous_deployment",
            "requires_approval": True,
            "payload_stored": False,
            "sensitive_values_stored": False,
        },
        "logs": {
            "available": "logs" in capabilities,
            "link": flow_links.get("logs", ""),
            "related_pods": len(pods),
        },
        "workload_refs": [
            {"id": f"workload_{item.id}", "name": item.name, "kind": item.kind} for item in workloads[:10]
        ],
        "links": flow_links,
        "capabilities": capabilities,
        "policy": {
            "mode": "read_only",
            "change_path": "devtron_rollback_or_deploy",
            "values_body_returned": False,
            "external_ui": "staff_admin_fallback",
        },
    }


def _values_preview(labels: dict[str, Any]) -> dict[str, Any]:
    raw_values = (
        labels.get("values") or labels.get("helm_values") or labels.get("helmValues") or labels.get("values_yaml")
    )
    preview = _safe_payload(raw_values) if raw_values not in (None, "") else {}
    return {
        "available": bool(raw_values)
        or bool(_label_value(labels, "valuesDigest", "values_digest", "devtron.ai/values-digest")),
        "visible": bool(raw_values),
        "body_returned": False,
        "redacted": bool(raw_values),
        "digest": _label_value(labels, "valuesDigest", "values_digest", "devtron.ai/values-digest"),
        "preview": preview if isinstance(preview, dict) else {},
    }


def _history_evidence(labels: dict[str, Any]) -> dict[str, Any]:
    return {
        "deployment_id": _label_value(labels, "devtron.ai/deployment-id", "deployment_id", "deploymentId"),
        "deployed_at": _label_value(labels, "devtron.ai/deployed-at", "deployed_at", "deployedAt"),
        "deployed_by": _label_value(labels, "devtron.ai/deployed-by", "deployed_by", "deployedBy"),
    }


def _label_value(labels: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = str(labels.get(key) or "").strip()
        if value:
            return _redact_log_line(value)[:MAX_TEXT_LENGTH]
    return ""


def _event_payload(event: K8sEvent | K8sAuditEvent) -> dict[str, Any]:
    if isinstance(event, K8sEvent):
        return serialize_kubernetes_event(event)
    return serialize_cluster_event(event)


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
    for value in values:
        candidate = value.lower()
        if normalized == candidate or normalized.startswith(f"{candidate}-"):
            return True
    return False


def _labels_match(labels: Any, values: set[str]) -> bool:
    if not isinstance(labels, dict):
        return False
    for key in APP_LABEL_KEYS:
        value = str(labels.get(key) or "").strip()
        if value and value in values:
            return True
    return False


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
