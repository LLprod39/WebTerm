from __future__ import annotations

from typing import Any

from kubernetes_ops.services.admin_resource_type_summary import type_specific_resource_summaries

MAX_SUMMARY_CONDITIONS = 8


def attach_resource_summaries(items: list[dict[str, Any]], *, ref) -> list[dict[str, Any]]:
    return [{**item, "summary": build_resource_row_summary(item, ref=ref)} for item in items]


def build_resource_row_summary(resource: dict[str, Any], *, ref) -> dict[str, Any]:
    metadata = resource.get("metadata") if isinstance(resource.get("metadata"), dict) else {}
    spec = resource.get("spec") if isinstance(resource.get("spec"), dict) else {}
    status = resource.get("status") if isinstance(resource.get("status"), dict) else {}
    pod_statuses = _pod_container_statuses(status)
    conditions = _conditions(status)
    return {
        "api_version": _text(resource.get("apiVersion") or getattr(ref, "api_version", ""), 80),
        "kind": _text(resource.get("kind") or getattr(ref, "kind", ""), 80),
        "resource": _text(getattr(ref, "resource", ""), 120),
        "namespace": _text(metadata.get("namespace") or getattr(ref, "namespace", ""), 120),
        "name": _text(metadata.get("name") or getattr(ref, "name", ""), 180),
        "creation_timestamp": _text(metadata.get("creationTimestamp"), 80),
        "phase": _text(status.get("phase"), 80),
        "reason": _text(status.get("reason"), 160),
        "condition_count": len(conditions),
        "conditions": [_condition_payload(item) for item in conditions[:MAX_SUMMARY_CONDITIONS]],
        "conditions_truncated": len(conditions) > MAX_SUMMARY_CONDITIONS,
        "condition_summary": _condition_summary(conditions),
        "generation": metadata.get("generation"),
        "resource_version": _text(metadata.get("resourceVersion"), 120),
        "owner_references": _owner_references(metadata.get("ownerReferences")),
        "ready": _ready(status, pod_statuses),
        "replicas": _replicas(status, spec),
        "containers": _container_summary(spec, status, pod_statuses),
        "service": _service_summary(spec),
        "node": _node_summary(resource, spec, status),
        "workload": _workload_summary(spec, status),
        **type_specific_resource_summaries(resource, spec, status),
        "keys": {
            "labels": _keys(metadata.get("labels")),
            "annotations": _keys(metadata.get("annotations")),
            "spec": _keys(spec),
            "status": _keys(status),
        },
    }


def _ready(status: dict[str, Any], pod_statuses: list[dict[str, Any]]) -> bool | None:
    if pod_statuses:
        return all(bool(item.get("ready")) for item in pod_statuses)
    for condition in status.get("conditions") if isinstance(status.get("conditions"), list) else []:
        if isinstance(condition, dict) and str(condition.get("type") or "").lower() in {"ready", "available"}:
            return str(condition.get("status") or "").lower() == "true"
    if status.get("readyReplicas") is not None and status.get("replicas") is not None:
        return status.get("readyReplicas") == status.get("replicas")
    return None


def _replicas(status: dict[str, Any], spec: dict[str, Any]) -> dict[str, Any]:
    return {
        "desired": spec.get("replicas"),
        "current": status.get("replicas"),
        "ready": status.get("readyReplicas"),
        "available": status.get("availableReplicas"),
        "updated": status.get("updatedReplicas"),
    }


def _container_summary(spec: dict[str, Any], status: dict[str, Any], pod_statuses: list[dict[str, Any]]) -> dict[str, Any]:
    containers = _containers_from_spec(spec)
    init_containers = _init_containers_from_spec(spec)
    return {
        "count": len(containers),
        "names": [_text(item.get("name"), 120) for item in containers[:20] if isinstance(item, dict)],
        "init_count": len(init_containers),
        "images": _container_images(containers + init_containers),
        "ready": sum(1 for item in pod_statuses if item.get("ready")),
        "total": len(pod_statuses),
        "restarts": sum(int(item.get("restartCount") or 0) for item in pod_statuses),
        "pod_ip": _text(status.get("podIP"), 80),
        "host_ip": _text(status.get("hostIP"), 80),
        "node_name": _text(status.get("nodeName"), 180),
    }


def _service_summary(spec: dict[str, Any]) -> dict[str, Any]:
    ports = spec.get("ports") if isinstance(spec.get("ports"), list) else []
    return {
        "type": _text(spec.get("type"), 80),
        "cluster_ip": _text(spec.get("clusterIP"), 80),
        "ports": [
            {
                "name": _text(port.get("name"), 80),
                "port": port.get("port"),
                "target_port": port.get("targetPort"),
                "protocol": _text(port.get("protocol"), 20),
            }
            for port in ports[:12]
            if isinstance(port, dict)
        ],
    }


def _node_summary(resource: dict[str, Any], spec: dict[str, Any], status: dict[str, Any]) -> dict[str, Any]:
    if str(resource.get("kind") or "").lower() != "node":
        return {}
    ready = _ready(status, [])
    return {
        "ready": ready,
        "unschedulable": bool(spec.get("unschedulable")),
        "roles": _node_roles(resource.get("metadata") if isinstance(resource.get("metadata"), dict) else {}),
    }


def _workload_summary(spec: dict[str, Any], status: dict[str, Any]) -> dict[str, Any]:
    strategy = spec.get("strategy") if isinstance(spec.get("strategy"), dict) else {}
    return {
        "selector_keys": _keys(_selector_from_spec(spec)),
        "strategy": _text(strategy.get("type"), 80),
        "observed_generation": status.get("observedGeneration"),
    }


def _containers_from_spec(spec: dict[str, Any]) -> list[dict[str, Any]]:
    containers = spec.get("containers")
    if isinstance(containers, list):
        return [item for item in containers if isinstance(item, dict)]
    template = spec.get("template") if isinstance(spec.get("template"), dict) else {}
    pod_spec = template.get("spec") if isinstance(template.get("spec"), dict) else {}
    template_containers = pod_spec.get("containers")
    return [item for item in template_containers if isinstance(item, dict)] if isinstance(template_containers, list) else []


def _init_containers_from_spec(spec: dict[str, Any]) -> list[dict[str, Any]]:
    containers = spec.get("initContainers")
    if isinstance(containers, list):
        return [item for item in containers if isinstance(item, dict)]
    template = spec.get("template") if isinstance(spec.get("template"), dict) else {}
    pod_spec = template.get("spec") if isinstance(template.get("spec"), dict) else {}
    template_containers = pod_spec.get("initContainers")
    return [item for item in template_containers if isinstance(item, dict)] if isinstance(template_containers, list) else []


def _container_images(containers: list[dict[str, Any]]) -> list[str]:
    return [_text(item.get("image"), 240) for item in containers[:20] if isinstance(item, dict) and item.get("image")]


def _pod_container_statuses(status: dict[str, Any]) -> list[dict[str, Any]]:
    statuses = status.get("containerStatuses")
    return [item for item in statuses if isinstance(item, dict)] if isinstance(statuses, list) else []


def _conditions(status: dict[str, Any]) -> list[dict[str, Any]]:
    conditions = status.get("conditions")
    return [item for item in conditions if isinstance(item, dict)] if isinstance(conditions, list) else []


def _condition_payload(condition: dict[str, Any]) -> dict[str, str]:
    return {
        "type": _text(condition.get("type"), 120),
        "status": _text(condition.get("status"), 40),
        "reason": _text(condition.get("reason"), 160),
        "message": _text(condition.get("message"), 300),
        "last_transition_time": _text(condition.get("lastTransitionTime"), 80),
    }


def _condition_summary(conditions: list[dict[str, Any]]) -> dict[str, Any]:
    payloads = [_condition_payload(item) for item in conditions[:MAX_SUMMARY_CONDITIONS]]
    failing = [item for item in payloads if item["status"].lower() in {"false", "unknown"}]
    return {
        "ready": _condition_status(payloads, "Ready"),
        "available": _condition_status(payloads, "Available"),
        "progressing": _condition_status(payloads, "Progressing"),
        "failing_count": len(failing),
        "warning_count": sum(1 for item in failing if item["reason"]),
        "failing": failing[:4],
    }


def _condition_status(conditions: list[dict[str, str]], condition_type: str) -> str:
    for condition in conditions:
        if condition["type"].lower() == condition_type.lower():
            return condition["status"]
    return ""


def _selector_from_spec(spec: dict[str, Any]) -> dict[str, Any]:
    selector = spec.get("selector") if isinstance(spec.get("selector"), dict) else {}
    if isinstance(selector.get("matchLabels"), dict):
        return selector["matchLabels"]
    return selector


def _owner_references(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [
        {
            "api_version": _text(item.get("apiVersion"), 80),
            "kind": _text(item.get("kind"), 80),
            "name": _text(item.get("name"), 180),
            "controller": bool(item.get("controller")),
        }
        for item in value[:8]
        if isinstance(item, dict)
    ]


def _node_roles(metadata: dict[str, Any]) -> list[str]:
    labels = metadata.get("labels") if isinstance(metadata.get("labels"), dict) else {}
    prefix = "node-role.kubernetes.io/"
    return sorted(str(key).removeprefix(prefix) or "control-plane" for key in labels if str(key).startswith(prefix))[:20]


def _keys(value: Any) -> list[str]:
    return sorted(_safe_key(key) for key in value.keys())[:40] if isinstance(value, dict) else []


def _text(value: Any, limit: int) -> str:
    return str(value or "").strip()[:limit]


def _safe_key(value: Any) -> str:
    key = str(value or "")[:120]
    normalized = key.replace("-", "_").lower()
    if any(part in normalized for part in ("token", "secret", "password", "credential", "kubeconfig", "authorization", "api_key", "apikey")):
        return "[redacted]"
    return key
