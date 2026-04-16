# web_ui/settings package.
# Select environment via DJANGO_SETTINGS_MODULE:
#   web_ui.settings.development  — local dev (default in manage.py)
#   web_ui.settings.production   — production deployments
#   web_ui.settings.test         — pytest / CI
#
# All three re-export everything from web_ui.settings.base
# and apply environment-specific overrides.
