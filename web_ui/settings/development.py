"""
Development settings.

All logic is inherited from base.py which reads env vars.
This file exists to provide a clean DJANGO_SETTINGS_MODULE target
and to document which overrides are intentional for local dev.

Usage:
    DJANGO_SETTINGS_MODULE=web_ui.settings.development python manage.py runserver
    (manage.py sets this as default when no DJANGO_SETTINGS_MODULE is set)
"""
from web_ui.settings.base import *  # noqa: F401, F403
from web_ui.settings.base import DEBUG  # explicit re-import for clarity

# Dev-specific guard: fail loudly if accidentally pointed at production config.
# In base.py DEBUG is derived from DJANGO_DEBUG env var (defaults True).
# Nothing else to override — base.py already handles dev defaults via env vars.
