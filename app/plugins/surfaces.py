from __future__ import annotations

from app.plugins.catalog import project_plugin_catalog
from app.plugins.contracts import SURFACE_KINDS


def active_plugin_surfaces(enabled_plugin_ids: set[str]) -> dict[str, list[dict]]:
    grouped = {kind: [] for kind in sorted(SURFACE_KINDS)}
    for plugin in project_plugin_catalog(enabled_plugin_ids):
        plugin_id = str(plugin.get("id") or "")
        surfaces = plugin.get("surfaces") if isinstance(plugin.get("surfaces"), dict) else {}
        for kind in SURFACE_KINDS:
            items = surfaces.get(kind) if isinstance(surfaces.get(kind), list) else []
            grouped[kind].extend({"plugin_id": plugin_id, **item} for item in items if isinstance(item, dict))
    return grouped

