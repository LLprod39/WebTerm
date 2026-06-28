from __future__ import annotations

from threading import RLock

from app.plugins.contracts import PluginManifest


class PluginRegistryError(ValueError):
    pass


class PluginRegistry:
    def __init__(self) -> None:
        self._lock = RLock()
        self._manifests: dict[str, PluginManifest] = {}

    def register(self, manifest: PluginManifest, *, replace: bool = False) -> None:
        with self._lock:
            existing = self._manifests.get(manifest.id)
            if existing and not replace:
                raise PluginRegistryError(f"Plugin already registered: {manifest.id}")
            self._manifests[manifest.id] = manifest

    def get(self, plugin_id: str) -> PluginManifest | None:
        with self._lock:
            return self._manifests.get(plugin_id)

    def all(self) -> list[PluginManifest]:
        with self._lock:
            return sorted(self._manifests.values(), key=lambda item: item.id)

    def reset(self) -> None:
        with self._lock:
            self._manifests.clear()


plugin_registry = PluginRegistry()
