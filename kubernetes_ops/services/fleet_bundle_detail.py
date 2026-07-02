from __future__ import annotations

from typing import Any

from django.db.models import Q

from kubernetes_ops.models import K8sAppRef, K8sAuditEvent, K8sCluster, K8sEvent, K8sFleetBundle, K8sWorkloadRef
from kubernetes_ops.serializers import (
    serialize_app,
    serialize_cluster_event,
    serialize_fleet_bundle,
    serialize_kubernetes_event,
    serialize_workload,
)
from kubernetes_ops.services.logs import _redact_log_line


MAX_RELATED_APPS = 30
MAX_RELATED_WORKLOADS = 50
MAX_RELATED_EVENTS = 40
MAX_TEXT_LENGTH = 1_000
SENSITIVE_KEY_PARTS = ("token", "secret", "password", "credential", "kubeconfig", "authorization", "api_key", "apikey")
FLEET_LABEL_PREFIXES = ("fleet.cattle.io/", "objectset.rio.cattle.io/")
FLEET_LABEL_KEYS = (
    "fleet.cattle.io/bundle-id",
    "fleet.cattle.io/bundle-name",
    "objectset.rio.cattle.io/id",
    "objectset.rio.cattle.io/owner-name",
)
BLOCKED_ACTIONS = ("direct_apply", "direct_patch", "direct_delete", "direct_scale", "direct_restart")
REQUESTABLE_ACTIONS = ("fleet.rollout.pause", "fleet.rollout.resume", "gitops.create_merge_request")


def fleet_bundle_for_value(bundle_id: str) -> K8sFleetBundle | None:
    value = str(bundle_id or "").strip()
    prefix, _, numeric = value.partition("_")
    if prefix == "fleet" and numeric.isdigit():
        return K8sFleetBundle.objects.filter(id=int(numeric)).first()
    if value.isdigit():
        return K8sFleetBundle.objects.filter(id=int(value)).first()
    return K8sFleetBundle.objects.filter(name=value).first()


def build_fleet_bundle_detail(bundle: K8sFleetBundle, *, user=None) -> dict[str, Any]:
    apps = _related_apps(bundle)
    workloads = _related_workloads(bundle)
    events = _related_events(bundle, apps=apps, workloads=workloads)
    app_payloads = [_safe_payload(serialize_app(app, user=user)) for app in apps]
    workload_payloads = [_safe_payload(serialize_workload(workload, user=user)) for workload in workloads]
    event_payloads = [_safe_payload(_event_payload(event)) for event in events]
    return {
        "success": True,
        "mode": "read_only",
        "operation": "fleet_bundle_detail",
        "source": "normalized_inventory",
        "bundle": _safe_payload(serialize_fleet_bundle(bundle, user=user)),
        "apps": app_payloads,
        "workloads": workload_payloads,
        "events": event_payloads,
        "summary": _summary(bundle, apps=apps, workloads=workloads, events=events),
        "policy": {
            "mode": "read_only",
            "mutates_state": False,
            "source": "normalized_inventory",
            "change_path": "fleet_gitops_or_mr",
            "external_ui": "staff_admin_fallback",
            "blocked_actions": list(BLOCKED_ACTIONS),
            "requestable_actions": list(REQUESTABLE_ACTIONS),
        },
    }


def fleet_bundle_audit_payload(payload: dict[str, Any]) -> dict[str, Any]:
    bundle = payload.get("bundle") if isinstance(payload.get("bundle"), dict) else {}
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    return {
        "bundle_id": str(bundle.get("id") or ""),
        "bundle_name": str(bundle.get("name") or ""),
        "status": str(bundle.get("status") or ""),
        "app_count": int(summary.get("app_count") or 0),
        "workload_count": int(summary.get("workload_count") or 0),
        "event_count": int(summary.get("event_count") or 0),
    }


def _related_apps(bundle: K8sFleetBundle) -> list[K8sAppRef]:
    candidates = _candidate_values(bundle)
    rows = K8sAppRef.objects.filter(owner=K8sAppRef.OWNER_FLEET).select_related("cluster").order_by("cluster__name", "namespace", "name")[:200]
    return [app for app in rows if _row_matches(bundle, app.name, app.namespace, app.labels, candidates)][:MAX_RELATED_APPS]


def _related_workloads(bundle: K8sFleetBundle) -> list[K8sWorkloadRef]:
    candidates = _candidate_values(bundle)
    rows = K8sWorkloadRef.objects.select_related("cluster").order_by("cluster__name", "namespace", "kind", "name")[:300]
    matched: list[K8sWorkloadRef] = []
    for workload in rows:
        owner = str(workload.owner or "").lower()
        if "fleet" not in owner and not _has_fleet_metadata(workload.labels):
            continue
        if _row_matches(bundle, workload.name, workload.namespace, workload.labels, candidates):
            matched.append(workload)
    return matched[:MAX_RELATED_WORKLOADS]


def _related_events(
    bundle: K8sFleetBundle,
    *,
    apps: list[K8sAppRef],
    workloads: list[K8sWorkloadRef],
) -> list[K8sEvent | K8sAuditEvent]:
    names = {bundle.name, _short_name(bundle.name), *(app.name for app in apps), *(workload.name for workload in workloads)}
    namespaces = {item for item in [_target_namespace(bundle), *(app.namespace for app in apps), *(workload.namespace for workload in workloads)] if item}
    cluster_ids = {item for item in [*(app.cluster_id for app in apps), *(workload.cluster_id for workload in workloads)] if item}
    query = Q()
    for name in {name for name in names if name}:
        query |= Q(involved_name=name) | Q(message__icontains=name)
    if namespaces:
        query &= Q(namespace__in=namespaces)
    if cluster_ids:
        query &= Q(cluster_id__in=cluster_ids)
    native_events = list(K8sEvent.objects.filter(query).order_by("-last_seen_at", "-id")[:MAX_RELATED_EVENTS]) if query else []
    if native_events:
        return native_events
    audit_events = (
        K8sAuditEvent.objects.filter(
            Q(payload__bundle_id=f"fleet_{bundle.id}")
            | Q(payload__bundle_name=bundle.name)
            | Q(payload__target__bundle_id=f"fleet_{bundle.id}")
            | Q(payload__target__bundle_name=bundle.name)
        )
        .select_related("user", "cluster")
        .order_by("-created_at", "-id")[:MAX_RELATED_EVENTS]
    )
    return list(audit_events)


def _summary(
    bundle: K8sFleetBundle,
    *,
    apps: list[K8sAppRef],
    workloads: list[K8sWorkloadRef],
    events: list[K8sEvent | K8sAuditEvent],
) -> dict[str, Any]:
    warning_events = [event for event in events if isinstance(event, K8sEvent) and event.severity in {K8sEvent.SEVERITY_WARNING, K8sEvent.SEVERITY_ERROR}]
    clusters = sorted({*(app.cluster.name for app in apps), *(workload.cluster.name for workload in workloads)})
    namespaces = sorted({*(app.namespace for app in apps), *(workload.namespace for workload in workloads)})
    return {
        "status": bundle.status,
        "ready": bundle.ready,
        "desired": bundle.desired,
        "partition_count": len(bundle.partitions or []) if isinstance(bundle.partitions, list) else 0,
        "app_count": len(apps),
        "workload_count": len(workloads),
        "event_count": len(events),
        "warning_event_count": len(warning_events),
        "unhealthy_app_count": sum(1 for app in apps if app.health != K8sCluster.HEALTH_HEALTHY),
        "unhealthy_workload_count": sum(1 for workload in workloads if workload.health != K8sCluster.HEALTH_HEALTHY),
        "ready_workloads": sum(1 for workload in workloads if workload.desired and workload.ready >= workload.desired),
        "desired_workloads": len(workloads),
        "clusters": clusters,
        "namespaces": namespaces,
        "source": bundle.source,
        "target": bundle.target,
    }


def _row_matches(bundle: K8sFleetBundle, name: str, namespace: str, labels: Any, candidates: set[str]) -> bool:
    if _labels_match(labels, candidates):
        return True
    short_name = _short_name(bundle.name)
    target_namespace = _target_namespace(bundle)
    if target_namespace and namespace == target_namespace:
        return True
    if short_name and (name == short_name or name.startswith(f"{short_name}-")):
        return True
    return False


def _candidate_values(bundle: K8sFleetBundle) -> set[str]:
    values = {bundle.name, _short_name(bundle.name), _target_namespace(bundle)}
    if isinstance(bundle.labels, dict):
        for key in FLEET_LABEL_KEYS:
            values.add(str(bundle.labels.get(key) or ""))
    return {value for value in (str(item or "").strip() for item in values) if value}


def _labels_match(labels: Any, candidates: set[str]) -> bool:
    if not isinstance(labels, dict):
        return False
    for key, value in labels.items():
        key_text = str(key)
        value_text = str(value or "").strip()
        if key_text in FLEET_LABEL_KEYS and _candidate_matches(value_text, candidates):
            return True
        if key_text.startswith(FLEET_LABEL_PREFIXES) and _candidate_matches(value_text, candidates):
            return True
        if key_text == "app.kubernetes.io/managed-by" and value_text.lower() == "fleet":
            app_name = str(labels.get("app.kubernetes.io/name") or labels.get("app.kubernetes.io/instance") or labels.get("app") or "")
            if _candidate_matches(app_name, candidates):
                return True
    return False


def _has_fleet_metadata(labels: Any) -> bool:
    if not isinstance(labels, dict):
        return False
    return any(str(key).startswith(FLEET_LABEL_PREFIXES) for key in labels) or str(labels.get("app.kubernetes.io/managed-by") or "").lower() == "fleet"


def _candidate_matches(value: str, candidates: set[str]) -> bool:
    text = str(value or "").strip()
    if not text:
        return False
    if text in candidates:
        return True
    short_text = _short_name(text)
    return bool(short_text and short_text in candidates)


def _short_name(value: str) -> str:
    text = str(value or "").strip()
    return text.rsplit("/", 1)[-1] if "/" in text else text


def _target_namespace(bundle: K8sFleetBundle) -> str:
    target = str(bundle.target or "").strip()
    if not target or any(char in target for char in "*[],{}"):
        return ""
    return target


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
        return [_safe_payload(item, depth=depth + 1) for item in value[:MAX_RELATED_WORKLOADS]]
    if isinstance(value, str):
        redacted = _redact_log_line(value)
        if len(redacted) > MAX_TEXT_LENGTH:
            return f"{redacted[:MAX_TEXT_LENGTH]}...[truncated]"
        return redacted
    return value


def _is_sensitive_key(key: str) -> bool:
    normalized = str(key or "").replace("-", "_").lower()
    return any(part in normalized for part in SENSITIVE_KEY_PARTS)
