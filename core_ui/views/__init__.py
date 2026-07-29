"""
core_ui/views — Views package.

Current state: auth, health, page, dashboard/terminal helpers live in focused modules; _views_all.py keeps legacy groups.
Target structure (split progressively):
  auth.py        — login, logout, session, csrf
  health.py      — health/readiness checks
  pages.py       — legacy Django-rendered page views
  access.py      — users, groups, permissions CRUD
  settings.py    — api_settings, api_models, api_models_refresh
  admin.py       — dashboard, activity, sessions
  chat.py        — chat sessions and streaming assistant API
  redirects.py   — frontend_*_redirect

core_ui/urls.py imports `from . import views` which resolves to this package.
"""

from core_ui.views._views_all import *  # noqa: F401, F403, F405
from core_ui.views.access_group_views import *  # noqa: F401, F403
from core_ui.views.access_views import *  # noqa: F401, F403
from core_ui.views.admin_billing import *  # noqa: F401, F403
from core_ui.views.admin_views import *  # noqa: F401, F403
from core_ui.views.auth_views import *  # noqa: F401, F403
from core_ui.views.chat_helpers import *  # noqa: F401, F403
from core_ui.views.chat_views import *  # noqa: F401, F403
from core_ui.views.dashboard_layout import api_dashboard_layout  # noqa: F401
from core_ui.views.health_views import *  # noqa: F401, F403
from core_ui.views.ide_views import *  # noqa: F401, F403
from core_ui.views.model_views import *  # noqa: F401, F403
from core_ui.views.page_views import *  # noqa: F401, F403
from core_ui.views.rag_views import *  # noqa: F401, F403
from core_ui.views.runtime import get_orchestrator, get_rag_engine, get_unified_orchestrator  # noqa: F401
from core_ui.views.settings_activity_views import *  # noqa: F401, F403
from core_ui.views.settings_config_views import *  # noqa: F401, F403
from core_ui.views.settings_page_views import *  # noqa: F401, F403
from core_ui.views.terminal_preferences import api_terminal_preferences  # noqa: F401
from core_ui.views.utility_views import *  # noqa: F401, F403
