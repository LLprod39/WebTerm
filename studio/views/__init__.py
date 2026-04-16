"""
studio/views — Views package.

Current state: all views are in _views_all.py (transition step).
Target structure (split progressively):
  pipeline_views.py      — pipeline CRUD + run + clone
  run_views.py           — run detail, stop, approve
  agent_views.py         — agent config CRUD
  skill_views.py         — skill authoring, templates, workspace
  mcp_views.py           — MCP pool CRUD + test + tools
  trigger_views.py       — trigger CRUD + webhook receive
  notification_views.py  — notification settings + test

studio/urls.py imports `from . import views` which resolves to this package.
"""
from studio.views._views_all import *  # noqa: F401, F403, F405

# Explicit re-exports of private helpers consumed by core_ui.desktop_api.views
from studio.views._views_all import (  # noqa: F401
    _normalize_sse_url,
    _test_mcp_connection,
)
