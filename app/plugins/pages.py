from __future__ import annotations

from app.plugins.catalog import project_plugin_catalog


def active_plugin_pages(enabled_plugin_ids: set[str]) -> list[dict]:
    pages: list[dict] = []
    for plugin in project_plugin_catalog(enabled_plugin_ids):
        for page in plugin.get("surfaces", {}).get("pages", []):
            pages.append({"plugin_id": plugin["id"], **page})
    return pages
