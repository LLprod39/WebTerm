from __future__ import annotations

from typing import Any

from app.plugins.contracts import PluginManifest, SURFACE_KINDS
from app.plugins.validation import validate_plugin_manifest


def manifest_from_dict(raw: dict[str, Any]) -> PluginManifest:
    return validate_plugin_manifest(raw)


def declared_surfaces(manifest: PluginManifest | dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    payload = manifest.to_dict(include_surfaces=True) if isinstance(manifest, PluginManifest) else manifest
    surfaces = payload.get("surfaces") if isinstance(payload.get("surfaces"), dict) else {}
    return {
        kind: [item for item in surfaces.get(kind, []) if isinstance(item, dict)]
        for kind in sorted(SURFACE_KINDS)
    }

