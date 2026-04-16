"""
servers/views — Views package.

Current state: all views are in _views_all.py (transition step).
Target structure (split progressively, one PR per domain):
  server_crud.py      — CRUD: create, update, delete, get, test_connection
  server_groups.py    — Group CRUD + members + subscribe
  server_files.py     — SFTP: file_list, read, write, chmod, upload, download
  server_linux_ui.py  — Linux UI: services, processes, logs, disk, docker
  server_knowledge.py — Knowledge base + memory snapshots
  server_monitoring.py — Health, alerts, watchers, ai_analyze
  server_agents.py    — Agent CRUD + runs + approve + task editing
  server_misc.py      — bootstrap, terminal pages, master_password, bulk_update

servers/urls.py imports `from . import views` which resolves to this package.
__init__.py re-exports everything so urls.py stays untouched.
"""
from servers.views._views_all import *  # noqa: F401, F403, F405
from servers.views.command_history import api_command_suggestions  # noqa: F401

# Explicit re-exports of private helpers consumed by core_ui.desktop_api.views
from servers.views._views_all import (  # noqa: F401
    _accessible_servers_queryset,
    _active_server_share,
    _active_share_q,
    _get_group_role,
    _require_ssh_server,
    _resolve_server_secret,
    _shared_server_context_allowed,
)
