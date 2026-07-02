from __future__ import annotations

from typing import Any

from kubernetes_ops.services.normalizers import payload_items


def crd_discovery_payload(payload: dict[str, Any], *, limit: int) -> dict[str, Any]:
    raw_items = payload_items(payload)
    resources: list[dict[str, Any]] = []
    truncated = len(raw_items) > limit
    for item in raw_items:
        if len(resources) >= limit:
            truncated = True
            break
        resources.extend(_resource_entries(item, remaining=limit - len(resources)))
    return {
        "status": "ready",
        "source": "custom_resource_definitions",
        "schema_included": False,
        "items": resources,
        "item_count": len(resources),
        "truncated": truncated,
    }


def _resource_entries(item: Any, *, remaining: int) -> list[dict[str, Any]]:
    if not isinstance(item, dict) or remaining <= 0:
        return []
    spec = item.get("spec") if isinstance(item.get("spec"), dict) else {}
    names = spec.get("names") if isinstance(spec.get("names"), dict) else {}
    group = _clean(spec.get("group"))
    kind = _clean(names.get("kind"))
    plural = _clean(names.get("plural")).lower()
    if not group or not kind or not plural:
        return []
    scope = _clean(spec.get("scope")) or "Namespaced"
    metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
    entries = []
    for version in _served_versions(spec):
        if len(entries) >= remaining:
            break
        version_name = _clean(version.get("name"))
        if not version_name:
            continue
        entries.append(
            {
                "api_version": f"{group}/{version_name}",
                "group": group,
                "version": version_name,
                "kind": kind,
                "resource": plural,
                "namespaced": scope.lower() != "cluster",
                "scope": "Cluster" if scope.lower() == "cluster" else "Namespaced",
                "short_names": _string_list(names.get("shortNames")),
                "categories": _string_list(names.get("categories")),
                "storage": bool(version.get("storage")),
                "crd_name": _clean(metadata.get("name")),
            }
        )
    return entries


def _served_versions(spec: dict[str, Any]) -> list[dict[str, Any]]:
    versions = spec.get("versions")
    if isinstance(versions, list):
        return [item for item in versions if isinstance(item, dict) and item.get("served", True)]
    legacy = _clean(spec.get("version"))
    return [{"name": legacy, "served": True, "storage": True}] if legacy else []


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [_clean(item) for item in value[:20] if _clean(item)]


def _clean(value: Any) -> str:
    return str(value or "").strip()[:160]
