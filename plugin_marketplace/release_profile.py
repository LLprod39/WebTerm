from __future__ import annotations

from typing import Any

from django.conf import settings

PLUGIN_MARKETPLACE_MODE_DISABLED = "disabled"
PLUGIN_MARKETPLACE_MODE_ENABLED = "enabled"
PLUGIN_MARKETPLACE_RELEASE_MODES = frozenset({PLUGIN_MARKETPLACE_MODE_DISABLED, PLUGIN_MARKETPLACE_MODE_ENABLED})


def plugin_marketplace_release_mode(settings_obj: Any = settings) -> str:
    """Return the normalized product release mode for plugin capabilities."""
    return (
        str(
            getattr(
                settings_obj,
                "PLUGIN_MARKETPLACE_RELEASE_MODE",
                PLUGIN_MARKETPLACE_MODE_DISABLED,
            )
            or PLUGIN_MARKETPLACE_MODE_DISABLED
        )
        .strip()
        .lower()
    )


def plugin_marketplace_enabled(settings_obj: Any = settings) -> bool:
    """Fail closed for unknown and explicitly disabled release modes."""
    return plugin_marketplace_release_mode(settings_obj) == PLUGIN_MARKETPLACE_MODE_ENABLED
