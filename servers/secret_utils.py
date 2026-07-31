from __future__ import annotations

from core_ui.managed_secrets import (
    get_server_auth_secret as get_managed_server_auth_secret,
)
from core_ui.managed_secrets import (
    get_server_sudo_secret as get_managed_server_sudo_secret,
)
from core_ui.managed_secrets import (
    has_server_auth_secret,
    has_server_sudo_secret,
)
from core_ui.managed_secrets import (
    set_server_auth_secret as set_managed_server_auth_secret,
)
from core_ui.managed_secrets import (
    set_server_sudo_secret as set_managed_server_sudo_secret,
)


def _invalidate_server_pool(server) -> None:
    from servers.services.ssh_pool import invalidate_ssh_connections

    if getattr(server, "pk", None):
        invalidate_ssh_connections(server.pk)


def has_saved_server_secret(server) -> bool:
    return bool(has_server_auth_secret(server.id))


def has_saved_server_sudo_secret(server) -> bool:
    return bool(has_server_sudo_secret(server.id))


def has_managed_server_secret(server) -> bool:
    return bool(has_server_auth_secret(server.id))


def has_managed_server_sudo_secret(server) -> bool:
    return bool(has_server_sudo_secret(server.id))


def server_secret_storage_mode(server) -> str:
    return "managed" if has_managed_server_secret(server) else "none"


def server_sudo_secret_storage_mode(server) -> str:
    return "managed" if has_managed_server_sudo_secret(server) else "none"


def get_server_auth_secret(server, *, master_password: str = "", fallback_plain: str = "") -> str:
    managed_secret = get_managed_server_auth_secret(server.id)
    if managed_secret:
        return managed_secret
    return fallback_plain or ""


def get_server_sudo_secret(server, *, master_password: str = "", fallback_plain: str = "") -> str:
    managed_secret = get_managed_server_sudo_secret(server.id)
    if managed_secret:
        return managed_secret

    return fallback_plain or ""


def store_server_auth_secret(server, *, secret_value: str, master_password: str = "") -> None:
    if server.auth_method not in ("password", "key_password"):
        return
    secret = (secret_value or "").strip()
    set_managed_server_auth_secret(server.id, secret)
    server.salt = None
    server.encrypted_password = ""
    _invalidate_server_pool(server)


def store_server_sudo_secret(server, *, secret_value: str, master_password: str = "") -> None:
    secret = (secret_value or "").strip()
    set_managed_server_sudo_secret(server.id, secret)
    server.sudo_salt = None
    server.encrypted_sudo_password = ""
    _invalidate_server_pool(server)


def clear_server_auth_secret(server) -> None:
    set_managed_server_auth_secret(server.id, "")
    server.salt = None
    server.encrypted_password = ""
    _invalidate_server_pool(server)


def clear_server_sudo_secret(server) -> None:
    set_managed_server_sudo_secret(server.id, "")
    server.sudo_salt = None
    server.encrypted_sudo_password = ""
    _invalidate_server_pool(server)
