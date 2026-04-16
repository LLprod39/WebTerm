"""
core_ui/views — Views package.

Current state: all views are in _views_all.py (transition step).
Target structure (split progressively):
  auth.py        — login, logout, session, csrf, ws-token
  access.py      — users, groups, permissions CRUD
  settings.py    — api_settings, api_models, api_models_refresh
  admin.py       — dashboard, activity, sessions
  redirects.py   — frontend_*_redirect

core_ui/urls.py imports `from . import views` which resolves to this package.
"""
from core_ui.views._views_all import *  # noqa: F401, F403, F405
from core_ui.views.terminal_preferences import api_terminal_preferences  # noqa: F401
