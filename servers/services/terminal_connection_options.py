"""
SSH connection option helpers for terminal sessions.

This is a small lifecycle extraction: the consumer still owns opening the PTY,
but host-key resolution and timeout/keepalive option assembly live in a
testable service.
"""

from __future__ import annotations

from typing import Any

from django.conf import settings

from servers.ssh_host_keys import build_server_connect_kwargs, ensure_server_known_hosts


def _positive_int_setting(name: str, default: int) -> int:
    return max(1, int(getattr(settings, name, default) or default))


async def build_terminal_connect_kwargs(server: Any, *, secret: str) -> dict[str, Any]:
    known_hosts = await ensure_server_known_hosts(server)
    return build_server_connect_kwargs(
        server,
        secret=secret or "",
        known_hosts=known_hosts,
        connect_timeout=_positive_int_setting("SSH_CONNECT_TIMEOUT_SECONDS", 10),
        login_timeout=_positive_int_setting("SSH_LOGIN_TIMEOUT_SECONDS", 20),
        keepalive_interval=_positive_int_setting("SSH_KEEPALIVE_INTERVAL_SECONDS", 20),
        keepalive_count_max=_positive_int_setting("SSH_KEEPALIVE_COUNT_MAX", 3),
    )
