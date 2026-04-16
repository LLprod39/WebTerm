"""
servers/services — Business-logic service layer (ARCHITECTURE_CONTRACT §3.1).

Rules:
  - Services are plain Python functions/classes; no HTTP knowledge.
  - Views import from services, never inline the logic.
  - Services may call ORM, app.tools, app.agent_kernel — but NOT views.

Modules:
  server_query.py    — get_server(), get_servers_for_user() — public API
  agent_service.py   — re-exports from servers.agent_service (existing)
  memory_service.py  — run_dreams(), purge_memory(), get_overview()
  monitor_service.py — check_health(), resolve_alert()
"""
# Re-export existing service functions so consumers can use
# `from servers.services import start_agent_run_for_user` etc.
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
