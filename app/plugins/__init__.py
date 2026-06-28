"""Pure plugin runtime contracts and registries."""

from app.plugins.catalog import ensure_builtin_plugins_registered
from app.plugins.contracts import PluginManifest
from app.plugins.discovery import declared_surfaces, manifest_from_dict
from app.plugins.registry import plugin_registry
from app.plugins.surfaces import active_plugin_surfaces

__all__ = [
    "PluginManifest",
    "active_plugin_surfaces",
    "declared_surfaces",
    "ensure_builtin_plugins_registered",
    "manifest_from_dict",
    "plugin_registry",
]
