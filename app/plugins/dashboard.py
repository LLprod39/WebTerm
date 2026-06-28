from __future__ import annotations

from app.plugins.catalog import project_plugin_catalog


def active_dashboard_widgets(enabled_plugin_ids: set[str]) -> list[dict]:
    widgets: list[dict] = []
    for plugin in project_plugin_catalog(enabled_plugin_ids):
        for widget in plugin.get("surfaces", {}).get("dashboard_widgets", []):
            widgets.append({"plugin_id": plugin["id"], **widget})
    return widgets
