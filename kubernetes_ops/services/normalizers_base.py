from __future__ import annotations

from typing import Any

from django.utils.dateparse import parse_datetime

from kubernetes_ops.models import (
    K8sCluster,
    K8sEvent,
    K8sFleetBundle,
    K8sWorkloadRef,
)


def payload_items(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []
    list_keys = (
        "data",
        "items",
        "result",
        "apps",
        "helmApps",
        "applications",
        "appList",
        "clusters",
        "bundles",
        "pods",
        "services",
        "ingresses",
    )
    for key in list_keys:
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    for key in ("data", "result"):
        value = payload.get(key)
        if isinstance(value, dict):
            nested_items = payload_items(value)
            if nested_items:
                return nested_items
    return []


def nested(item: dict[str, Any], *keys: str) -> Any:
    current: Any = item
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def first_value(item: dict[str, Any], *paths: str, default: Any = "") -> Any:
    for path in paths:
        parts = path.split(".")
        value = nested(item, *parts)
        if value not in (None, ""):
            return value
    return default


def as_int(value: Any, default: int = 0) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed >= 0 else default


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def labels_for(item: dict[str, Any]) -> dict[str, Any]:
    value = item.get("labels") or nested(item, "metadata", "labels") or {}
    return dict(value) if isinstance(value, dict) else {}


def infer_environment(name: str, labels: dict[str, Any], explicit: str = "") -> str:
    for key in ("webterm.io/environment", "environment", "env"):
        value = str(labels.get(key) or "").strip()
        if value:
            return value
    explicit = explicit.strip()
    if explicit:
        return explicit
    prefix = name.split("-", 1)[0].lower()
    return prefix if prefix in {"dev", "stage", "staging", "prod", "production", "test"} else ""


def normalize_health(value: Any) -> str:
    text = str(value or "").strip().lower()
    if text in {"active", "ready", "running", "healthy", "ok", "success", "available", "deployed"}:
        return K8sCluster.HEALTH_HEALTHY
    if text in {"updating", "provisioning", "pending", "progressing", "warning", "degraded-but-available"}:
        return K8sCluster.HEALTH_WARNING
    if text in {"error", "failed", "degraded", "unavailable", "notready", "not_ready", "critical"}:
        return K8sCluster.HEALTH_DEGRADED
    return K8sCluster.HEALTH_UNKNOWN


def normalize_fleet_status(value: Any) -> str:
    text = str(value or "").strip().lower()
    if text in {"ready", "active", "healthy", "success"}:
        return K8sFleetBundle.STATUS_READY
    if text in {"rolling", "updating", "pending", "progressing", "modified", "waitapplied"}:
        return K8sFleetBundle.STATUS_ROLLING
    if text in {"paused", "suspended"}:
        return K8sFleetBundle.STATUS_PAUSED
    if text in {"failed", "degraded", "error", "notready"}:
        return K8sFleetBundle.STATUS_DEGRADED
    return K8sFleetBundle.STATUS_UNKNOWN


def normalize_workload_kind(value: Any) -> str:
    text = str(value or "").strip().lower()
    if ":" in text:
        text = text.split(":", 1)[0]
    text = text.removeprefix("apps.").removesuffix("s")
    aliases = {
        "deployment": K8sWorkloadRef.KIND_DEPLOYMENT,
        "statefulset": K8sWorkloadRef.KIND_STATEFULSET,
        "daemonset": K8sWorkloadRef.KIND_DAEMONSET,
        "cronjob": K8sWorkloadRef.KIND_CRONJOB,
        "job": K8sWorkloadRef.KIND_JOB,
        "pod": K8sWorkloadRef.KIND_POD,
    }
    return aliases.get(text, K8sWorkloadRef.KIND_UNKNOWN)


def normalize_event_severity(value: Any) -> str:
    text = str(value or "").strip().lower()
    if text in {"warning", "warn"}:
        return K8sEvent.SEVERITY_WARNING
    if text in {"error", "failed", "failure", "critical"}:
        return K8sEvent.SEVERITY_ERROR
    return K8sEvent.SEVERITY_INFO


def parse_event_time(value: Any):
    if not value:
        return None
    parsed = parse_datetime(str(value))
    return parsed


def split_rancher_ref(value: Any) -> list[str]:
    text = str(value or "").strip()
    return [part for part in text.split(":") if part]


def compact_strings(values: list[Any], limit: int = 20) -> list[str]:
    result = []
    for value in values:
        text = str(value or "").strip()
        if text and text not in result:
            result.append(text)
        if len(result) >= limit:
            break
    return result


def bounded_text(value: Any, limit: int) -> str:
    text = str(value or "").strip()
    return text[:limit]
