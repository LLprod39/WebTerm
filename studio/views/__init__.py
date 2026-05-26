"""
studio/views — Views package.

Current state: endpoint groups live in focused modules; _views_all.py keeps shared compatibility helpers.
Target structure (split progressively):
  pipeline_views.py      — pipeline CRUD + run + clone
  pipeline_assistant_views.py — pipeline graph assistant endpoint
  run_views.py           — run detail, stop, approve
  agent_views.py         — agent config CRUD
  skill_views.py         — skill authoring, templates, workspace
  mcp_views.py           — MCP pool CRUD + test + tools
  share_views.py         — shared user lookup helpers
  trigger_views.py       — trigger CRUD + webhook receive
  template_views.py      — pipeline templates + instantiate
  server_views.py        — server dropdown payloads
  notification_views.py  — notification settings + test

Legacy callers can still import endpoint functions and private compatibility hooks from `studio.views`.
"""
from studio.views._views_all import *  # noqa: F401, F403, F405

# Explicit re-exports of private helpers consumed by core_ui.desktop_api.views
from studio.views._views_all import (  # noqa: F401
    _launch_pipeline_run_async,
)
from studio.views.agent_views import *  # noqa: F401, F403
from studio.views.mcp_views import *  # noqa: F401, F403
from studio.views.mcp_views import _normalize_sse_url, _test_mcp_connection  # noqa: F401
from studio.views.notification_views import *  # noqa: F401, F403
from studio.views.notification_views import _NOTIF_CONFIG_PATH, _load_notif_config  # noqa: F401
from studio.views.pipeline_assistant_views import *  # noqa: F401, F403
from studio.views.pipeline_views import *  # noqa: F401, F403
from studio.views.run_views import *  # noqa: F401, F403
from studio.views.server_views import *  # noqa: F401, F403
from studio.views.share_views import *  # noqa: F401, F403
from studio.views.skill_views import *  # noqa: F401, F403
from studio.views.template_views import *  # noqa: F401, F403
from studio.views.trigger_views import *  # noqa: F401, F403
