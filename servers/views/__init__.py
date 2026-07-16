"""
servers/views — Views package.

Current state: server view logic is split into focused modules. `_views_all.py`
is now only a compatibility shim for historical imports.
Target structure (split progressively, one PR per domain):
  server_pages.py     — SSR page views and SPA bootstrap
  server_helpers.py   — Shared access, share, OS serialization, and secret helpers
  server_crud.py      — Server create/update/delete/get/reveal
  server_ops.py       — Connection test, command execute, OS detect
  server_auth_session.py — Session master-password helper endpoints
  server_groups.py    — Group CRUD + members + subscribe
  server_shares.py    — Server share list/create/revoke
  server_context.py   — Global and group rules/context
  server_files.py     — SFTP: file_list, read, write, chmod, upload, download
  server_linux_ui.py  — Linux UI read-only snapshots: overview, logs, disk, network, packages
  server_linux_ui_workloads.py — Linux UI services, processes, docker, and actions
  server_knowledge.py — Knowledge base
  server_memory.py    — Layered memory snapshots, policy, promotions
  server_monitoring.py — Health, alerts, watchers, ai_analyze
  server_agents.py    — Agent CRUD + schedules + launch
  server_agent_runs.py — Agent runs + approve + task editing

servers/urls.py imports focused modules directly.
"""

from servers.encryption import PasswordEncryption  # noqa: F401
from servers.views.command_history import api_command_suggestions  # noqa: F401
from servers.views.server_agent_runs import *  # noqa: F401, F403
from servers.views.server_agents import *  # noqa: F401, F403
from servers.views.server_auth_session import *  # noqa: F401, F403
from servers.views.server_context import *  # noqa: F401, F403
from servers.views.server_crud import *  # noqa: F401, F403
from servers.views.server_files import *  # noqa: F401, F403
from servers.views.server_groups import *  # noqa: F401, F403

# Explicit re-exports of private compatibility helpers.
from servers.views.server_helpers import (  # noqa: F401
    _accessible_servers_queryset,
    _active_server_share,
    _active_share_q,
    _effective_master_password,
    _get_group_role,
    _require_ssh_server,
    _resolve_server_secret,
    _serialize_detected_os_fields,
    _shared_server_context_allowed,
)
from servers.views.server_insights import *  # noqa: F401, F403
from servers.views.server_knowledge import *  # noqa: F401, F403
from servers.views.server_linux_ui import *  # noqa: F401, F403
from servers.views.server_linux_ui_workloads import *  # noqa: F401, F403
from servers.views.server_memory import *  # noqa: F401, F403
from servers.views.server_monitoring import *  # noqa: F401, F403
from servers.views.server_monitoring_actions import *  # noqa: F401, F403
from servers.views.server_ops import *  # noqa: F401, F403
from servers.views.server_pages import *  # noqa: F401, F403
from servers.views.server_shares import *  # noqa: F401, F403
