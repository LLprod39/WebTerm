"""
Compatibility re-exports for the former core_ui.views monolith.

New code should import focused modules directly.
"""

from core_ui.views.admin_billing import (  # noqa: F401
    _extract_numeric_by_key,
    _fetch_anthropic_billing,
    _fetch_openai_billing,
    _fetch_xai_billing,
    _get_provider_billing_snapshot,
    _http_get_json,
    _sum_anthropic_costs,
    _sum_openai_costs,
    _to_float,
)
from core_ui.views.admin_views import *  # noqa: F401, F403
from core_ui.views.admin_views import (  # noqa: F401
    _admin_dashboard_view,
    _collect_admin_dashboard_data,
    _model_or_none,
)
from core_ui.views.chat_helpers import (  # noqa: F401
    _chat_history_from_session,
    _get_server_names_for_user,
    _get_servers_context_for_prompt,
    _load_session,
    _load_task_context_for_user,
    _resolve_cursor_cli_command,
    _stream_cursor_cli,
    _try_server_command_by_name,
)
from core_ui.views.chat_views import *  # noqa: F401, F403
from core_ui.views.chat_views import (  # noqa: F401
    _build_execution_context,
    _build_task_context_prompt,
    _save_chat_exchange,
)
from core_ui.views.settings_page_views import *  # noqa: F401, F403
