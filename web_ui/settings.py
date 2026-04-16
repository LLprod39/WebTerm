"""
DEPRECATED: Use web_ui.settings.development / .production / .test instead.

This file is kept as a backward-compatibility shim.
It re-exports everything from web_ui.settings.base so that any external
tool or deployment script that still references "web_ui.settings" continues
to work during the transition period.

Migration: replace DJANGO_SETTINGS_MODULE=web_ui.settings with:
  - web_ui.settings.development  (local dev)
  - web_ui.settings.production   (deployments, set DJANGO_DEBUG=false)
  - web_ui.settings.test         (pytest / CI)
"""
from web_ui.settings.base import *  # noqa: F401, F403
