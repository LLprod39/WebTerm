"""
servers/services — Business-logic service layer (ARCHITECTURE_CONTRACT §3.1).

Rules:
  - Services are plain Python functions/classes; no HTTP knowledge.
  - Views import from services, never inline the logic.
  - Services may call ORM, app.tools, app.agent_kernel — but NOT views.

Modules:
  alert_query.py    — get_alert_snapshot(), get_open_alert_snapshot() — public API
  server_query.py    — get_server(), get_servers_for_user() — public API
  tool_catalog.py   — list_agent_tool_names() — public API
  agent_service.py   — re-exports from servers.agent_service (existing)
  memory_service.py  — run_dreams(), purge_memory(), get_overview()
  monitor_service.py — check_health(), resolve_alert()
"""
from servers.agent_service import (  # noqa: F401
    approve_agent_plan_for_user,
    dispatch_scheduled_agents_for_user,
    launch_watcher_draft_for_user,
    list_agents_for_user,
    list_scheduled_agents_for_user,
    reply_to_agent_run_for_user,
    start_agent_run_for_user,
    stop_agent_run_for_user,
)
from servers.services.alert_query import (  # noqa: F401
    ServerAlertSnapshot,
    get_alert_snapshot,
    get_open_alert_snapshot,
)
from servers.services.pipeline_agents import (  # noqa: F401
    AgentRunSnapshot,
    run_pipeline_multi_agent,
    run_pipeline_react_agent,
)
from servers.services.pipeline_memory import (  # noqa: F401
    build_pipeline_operational_recipes,
    get_pipeline_server_card,
)
from servers.services.ssh_connection import get_server_connect_kwargs  # noqa: F401
from servers.services.tool_catalog import list_agent_tool_names  # noqa: F401
