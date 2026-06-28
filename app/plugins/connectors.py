from __future__ import annotations

from app.plugins.catalog import project_plugin_catalog


def active_connectors(enabled_plugin_ids: set[str]) -> list[dict]:
    connectors: list[dict] = []
    for plugin in project_plugin_catalog(enabled_plugin_ids):
        for connector in plugin.get("surfaces", {}).get("connectors", []):
            connectors.append({"plugin_id": plugin["id"], **connector})
    return connectors
