from __future__ import annotations

from typing import Any

READ_VERBS = ("get", "list", "watch")
MUTATING_VERBS = {"create", "update", "patch", "delete", "deletecollection"}

GROUP_LABELS = {
    "workloads": "Workloads",
    "network": "Network",
    "config": "Config",
    "storage": "Storage",
    "security": "Security",
    "policy": "Policy",
    "cluster": "Cluster",
    "custom": "Custom resources",
    "other": "Other",
}


def build_resource_catalog(
    *,
    common_resources: list[dict[str, Any]],
    api_resources: dict[str, Any],
    crd_resources: dict[str, Any],
    limit: int,
) -> dict[str, Any]:
    entries: dict[tuple[str, str], dict[str, Any]] = {}
    for item in common_resources:
        _merge(entries, item, source="common", cluster_available=False)
    for item in _items(api_resources):
        _merge(entries, item, source="api", cluster_available=True)
    for item in _items(crd_resources):
        _merge(entries, item, source="crd", cluster_available=True, custom=True)
    catalog_items = sorted(entries.values(), key=lambda item: (item["api_version"], item["kind"], item["resource"]))[
        :limit
    ]
    groups = _catalog_groups(catalog_items)
    return {
        "status": _catalog_status(api_resources, crd_resources),
        "source": "merged_common_api_crd_discovery",
        "items": catalog_items,
        "item_count": len(catalog_items),
        "counts": _catalog_counts(catalog_items),
        "groups": groups,
        "group_count": len(groups),
        "truncated": len(entries) > limit
        or bool(api_resources.get("truncated"))
        or bool(crd_resources.get("truncated")),
        "raw_payload_included": False,
    }


def resource_catalog_action_summary(catalog: dict[str, Any]) -> dict[str, int]:
    counts = catalog.get("counts") if isinstance(catalog.get("counts"), dict) else {}
    return {
        "resource_catalog_count": int(catalog.get("item_count") or 0),
        "resource_catalog_group_count": int(catalog.get("group_count") or 0),
        "resource_catalog_custom_count": int(counts.get("custom") or 0),
    }


def _merge(
    entries: dict[tuple[str, str], dict[str, Any]],
    item: dict[str, Any],
    *,
    source: str,
    cluster_available: bool,
    custom: bool = False,
) -> None:
    api_version = _clean(item.get("api_version")) or "v1"
    resource = _clean(item.get("resource")).lower()
    kind = _clean(item.get("kind"))
    if not resource or not kind:
        return
    key = (api_version, resource)
    entry = entries.setdefault(
        key,
        {
            "id": f"{api_version}:{resource}",
            "api_version": api_version,
            "group": _clean(item.get("group")) or _group(api_version),
            "version": _clean(item.get("version")) or _version(api_version),
            "kind": kind,
            "resource": resource,
            "namespaced": bool(item.get("namespaced")),
            "scope": "Namespaced" if item.get("namespaced") else "Cluster",
            "verbs": [],
            "short_names": [],
            "categories": [],
            "ui_group": _resource_group(api_version=api_version, kind=kind, resource=resource, custom=custom),
            "safe_read_actions": [],
            "has_mutating_verbs": False,
            "sources": [],
            "cluster_available": False,
            "custom": False,
            "query": {"api_version": api_version, "kind": kind, "resource": resource},
        },
    )
    entry["sources"] = _unique([*entry["sources"], source])
    entry["cluster_available"] = bool(entry["cluster_available"] or cluster_available)
    entry["custom"] = bool(entry["custom"] or custom)
    entry["namespaced"] = bool(entry["namespaced"] or item.get("namespaced"))
    entry["scope"] = "Namespaced" if entry["namespaced"] else "Cluster"
    entry["verbs"] = _unique([*entry["verbs"], *_string_list(item.get("verbs"))])
    entry["short_names"] = _unique(
        [*entry["short_names"], *_string_list(item.get("short_names") or item.get("shortNames"))]
    )
    entry["categories"] = _unique([*entry["categories"], *_string_list(item.get("categories"))])
    entry["ui_group"] = _resource_group(
        api_version=api_version, kind=kind, resource=resource, custom=bool(entry["custom"])
    )
    entry["safe_read_actions"] = _safe_read_actions(entry["verbs"], kind=kind)
    entry["has_mutating_verbs"] = any(verb in MUTATING_VERBS for verb in entry["verbs"])
    if item.get("singular_name"):
        entry["singular_name"] = _clean(item.get("singular_name"))
    if item.get("crd_name"):
        entry["crd_name"] = _clean(item.get("crd_name"))


def _catalog_status(api_resources: dict[str, Any], crd_resources: dict[str, Any]) -> str:
    statuses = {str(api_resources.get("status") or ""), str(crd_resources.get("status") or "")}
    if "partial" in statuses:
        return "partial"
    if "unavailable" in statuses:
        return "partial"
    return "ready"


def _items(payload: dict[str, Any]) -> list[dict[str, Any]]:
    items = payload.get("items")
    return [item for item in items if isinstance(item, dict)] if isinstance(items, list) else []


def _catalog_counts(items: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "total": len(items),
        "cluster_available": sum(1 for item in items if item.get("cluster_available")),
        "common": sum(1 for item in items if "common" in set(item.get("sources") or [])),
        "custom": sum(1 for item in items if item.get("custom")),
        "namespaced": sum(1 for item in items if item.get("namespaced")),
        "cluster_scoped": sum(1 for item in items if not item.get("namespaced")),
        "with_mutating_verbs": sum(1 for item in items if item.get("has_mutating_verbs")),
    }


def _catalog_groups(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[str, dict[str, Any]] = {}
    for item in items:
        group_id = _clean(item.get("ui_group")) or "other"
        group = groups.setdefault(
            group_id,
            {
                "id": group_id,
                "label": GROUP_LABELS.get(group_id, group_id.replace("_", " ").title()),
                "item_count": 0,
                "cluster_available_count": 0,
                "custom_count": 0,
                "namespaced_count": 0,
                "cluster_scoped_count": 0,
            },
        )
        group["item_count"] += 1
        group["cluster_available_count"] += 1 if item.get("cluster_available") else 0
        group["custom_count"] += 1 if item.get("custom") else 0
        group["namespaced_count"] += 1 if item.get("namespaced") else 0
        group["cluster_scoped_count"] += 0 if item.get("namespaced") else 1
    return sorted(groups.values(), key=lambda item: (item["label"], item["id"]))


def _safe_read_actions(verbs: list[str], *, kind: str) -> list[str]:
    verb_set = set(verbs)
    actions: list[str] = []
    if not verbs or "list" in verb_set:
        actions.append("list")
    if not verbs or "get" in verb_set:
        actions.extend(["detail", "yaml"])
    if "watch" in verb_set:
        actions.append("watch")
    if kind.lower() == "pod" and (not verbs or "get" in verb_set):
        actions.append("logs")
    return actions


def _resource_group(*, api_version: str, kind: str, resource: str, custom: bool) -> str:
    if custom:
        return "custom"
    kind_lower = kind.lower()
    resource_lower = resource.lower()
    group = _group(api_version)
    if kind_lower in {
        "pod",
        "deployment",
        "statefulset",
        "daemonset",
        "replicaset",
        "job",
        "cronjob",
        "horizontalpodautoscaler",
    }:
        return "workloads"
    if kind_lower in {"service", "ingress", "endpoints", "endpointslice", "networkpolicy"}:
        return "network"
    if kind_lower in {"configmap", "secret", "serviceaccount"}:
        return "config"
    if kind_lower in {"persistentvolumeclaim", "persistentvolume", "storageclass"}:
        return "storage"
    if (
        kind_lower in {"role", "rolebinding", "clusterrole", "clusterrolebinding"}
        or group == "rbac.authorization.k8s.io"
    ):
        return "security"
    if kind_lower in {"poddisruptionbudget", "resourcequota", "limitrange"} or group == "policy":
        return "policy"
    if kind_lower in {"namespace", "node", "customresourcedefinition"} or resource_lower == "namespaces":
        return "cluster"
    return "other"


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [_clean(item) for item in value[:40] if _clean(item)]


def _unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def _group(api_version: str) -> str:
    group, separator, _version_value = api_version.partition("/")
    return group if separator else ""


def _version(api_version: str) -> str:
    group, separator, version_value = api_version.partition("/")
    return version_value if separator else group


def _clean(value: Any) -> str:
    return str(value or "").strip()[:160]
