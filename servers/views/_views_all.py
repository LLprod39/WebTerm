"""
Legacy compatibility shim for historical `servers.views._views_all` imports.

Real view logic now lives in focused modules such as `server_pages.py`,
`server_helpers.py`, `server_crud.py`, and `server_ops.py`.
"""

from servers.encryption import PasswordEncryption  # noqa: F401
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
from servers.views.server_pages import (  # noqa: F401
    frontend_bootstrap,
    multi_terminal,
    server_list,
    server_terminal_page,
    terminal_minimal,
)
