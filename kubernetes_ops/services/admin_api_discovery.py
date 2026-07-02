from __future__ import annotations

from collections.abc import Callable
from typing import Any

MAX_DISCOVERY_GROUP_VERSIONS = 40


def api_resource_catalog_payload(
    core_payload: dict[str, Any],
    groups_payload: dict[str, Any],
    *,
    fetch_group_version: Callable[[str], dict[str, Any]],
    limit: int,
) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    failures: list[dict[str, str]] = []
    _append_api_resources(items, core_payload, api_version="v1", source="core", limit=limit)
    group_versions = _group_versions(groups_payload)[:MAX_DISCOVERY_GROUP_VERSIONS]
    for api_version in group_versions:
        if len(items) >= limit:
            break
        try:
            payload = fetch_group_version(api_version)
        except Exception as exc:
            failures.append({"api_version": api_version, "reason": type(exc).__name__[:80]})
            continue
        _append_api_resources(items, payload, api_version=api_version, source="group", limit=limit)
    return {
        "status": "partial" if failures else "ready",
        "source": "kubernetes_api_discovery",
        "raw_payload_included": False,
        "items": items,
        "item_count": len(items),
        "group_version_count": len(group_versions),
        "failed_group_versions": failures[:20],
        "truncated": len(items) >= limit or len(group_versions) > MAX_DISCOVERY_GROUP_VERSIONS,
    }


def _append_api_resources(items: list[dict[str, Any]], payload: dict[str, Any], *, api_version: str, source: str, limit: int) -> None:
    for resource in payload.get("resources") if isinstance(payload.get("resources"), list) else []:
        if len(items) >= limit:
            return
        normalized = _api_resource_item(resource, api_version=api_version, source=source)
        if normalized:
            items.append(normalized)


def _api_resource_item(resource: Any, *, api_version: str, source: str) -> dict[str, Any] | None:
    if not isinstance(resource, dict):
        return None
    name = _clean(resource.get("name")).lower()
    kind = _clean(resource.get("kind"))
    if not name or not kind or "/" in name:
        return None
    group, version = _split_api_version(api_version)
    return {
        "api_version": api_version,
        "group": group,
        "version": version,
        "kind": kind,
        "resource": name,
        "namespaced": bool(resource.get("namespaced")),
        "verbs": _string_list(resource.get("verbs"), limit=20),
        "short_names": _string_list(resource.get("shortNames"), limit=20),
        "categories": _string_list(resource.get("categories"), limit=20),
        "singular_name": _clean(resource.get("singularName")),
        "source": source,
    }


def _group_versions(payload: dict[str, Any]) -> list[str]:
    versions: list[str] = []
    for group in payload.get("groups") if isinstance(payload.get("groups"), list) else []:
        if not isinstance(group, dict):
            continue
        group_name = _clean(group.get("name"))
        if not group_name:
            continue
        preferred = group.get("preferredVersion") if isinstance(group.get("preferredVersion"), dict) else {}
        preferred_version = _clean(preferred.get("version"))
        if preferred_version:
            versions.append(f"{group_name}/{preferred_version}")
        for version in group.get("versions") if isinstance(group.get("versions"), list) else []:
            version_name = _clean(version.get("version")) if isinstance(version, dict) else ""
            if version_name:
                versions.append(f"{group_name}/{version_name}")
    return list(dict.fromkeys(versions))


def _split_api_version(api_version: str) -> tuple[str, str]:
    group, separator, version = api_version.partition("/")
    return (group, version) if separator else ("", group)


def _string_list(value: Any, *, limit: int) -> list[str]:
    if not isinstance(value, list):
        return []
    return [_clean(item) for item in value[:limit] if _clean(item)]


def _clean(value: Any) -> str:
    return str(value or "").strip()[:160]
