"""
SSH connection option helpers for terminal sessions.

This is a small lifecycle extraction: the consumer still owns opening the PTY,
but host-key resolution and timeout/keepalive option assembly live in a
testable service.
"""

from __future__ import annotations

from typing import Any

from asgiref.sync import sync_to_async
from django.conf import settings

from servers.ssh_host_keys import build_server_connect_kwargs, ensure_server_known_hosts
from servers.ssh_private_keys import get_server_private_key_text


def _positive_int_setting(name: str, default: int) -> int:
    return max(1, int(getattr(settings, name, default) or default))


async def build_terminal_connect_kwargs(server: Any, *, secret: str) -> dict[str, Any]:
    known_hosts = await ensure_server_known_hosts(server)
    private_key_text = ""
    if str(getattr(server, "auth_method", "") or "") in {"key", "key_password"}:
        private_key_text = await sync_to_async(get_server_private_key_text, thread_sensitive=True)(server)
    return build_server_connect_kwargs(
        server,
        secret=secret or "",
        private_key_text=private_key_text,
        known_hosts=known_hosts,
        connect_timeout=_positive_int_setting("SSH_CONNECT_TIMEOUT_SECONDS", 10),
        login_timeout=_positive_int_setting("SSH_LOGIN_TIMEOUT_SECONDS", 20),
        keepalive_interval=_positive_int_setting("SSH_KEEPALIVE_INTERVAL_SECONDS", 20),
        keepalive_count_max=_positive_int_setting("SSH_KEEPALIVE_COUNT_MAX", 3),
    )
