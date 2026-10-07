from __future__ import annotations

import os
from typing import Any

from loguru import logger

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
    if has_server_auth_secret(server.id):
        return True
    return bool(getattr(server, "encrypted_password", "") or "")


def has_saved_server_sudo_secret(server) -> bool:
    if has_server_sudo_secret(server.id):
        return True
    return bool(getattr(server, "encrypted_sudo_password", "") or "")


def has_managed_server_secret(server) -> bool:
    return bool(has_server_auth_secret(server.id))


def has_managed_server_sudo_secret(server) -> bool:
    return bool(has_server_sudo_secret(server.id))


def server_secret_storage_mode(server) -> str:
    if has_managed_server_secret(server):
        return "managed"
    if getattr(server, "encrypted_password", "") or "":
        return "legacy"
    return "none"


def server_sudo_secret_storage_mode(server) -> str:
    if has_managed_server_sudo_secret(server):
        return "managed"
    if getattr(server, "encrypted_sudo_password", "") or "":
        return "legacy"
    return "none"


def _resolve_master_password(master_password: str = "") -> str:
    value = (master_password or "").strip()
    if value:
        return value
    return str(os.environ.get("MASTER_PASSWORD") or "").strip()


def _decrypt_legacy_field(
    *,
    ciphertext: str,
    salt: Any,
    master_password: str,
    kind: str,
    server_id: int | None,
) -> str:
    encrypted = str(ciphertext or "").strip()
    if not encrypted or salt is None:
        return ""
    mp = _resolve_master_password(master_password)
    if not mp:
        return ""
    try:
        from servers.encryption import PasswordEncryption

        return PasswordEncryption.decrypt_password(encrypted, mp, bytes(salt))
    except Exception as exc:  # noqa: BLE001 — treat as missing secret
        logger.warning(
            "legacy {} secret decrypt failed for server_id={}: {}",
            kind,
            server_id,
            exc,
        )
        return ""


def _promote_legacy_auth_secret(server, secret: str) -> None:
    """Write ManagedSecret and clear legacy ciphertext when decrypt succeeds."""
    if not secret or not getattr(server, "pk", None):
        return
    try:
        set_managed_server_auth_secret(server.id, secret)
        from servers.models import Server

        Server.objects.filter(pk=server.pk).update(encrypted_password="", salt=None)
        server.encrypted_password = ""
        server.salt = None
        _invalidate_server_pool(server)
    except Exception as exc:  # noqa: BLE001 — SSH can still use the decrypted value
        logger.warning("legacy auth secret promote failed for server_id={}: {}", server.pk, exc)


def _promote_legacy_sudo_secret(server, secret: str) -> None:
    if not secret or not getattr(server, "pk", None):
        return
    try:
        set_managed_server_sudo_secret(server.id, secret)
        from servers.models import Server

        Server.objects.filter(pk=server.pk).update(encrypted_sudo_password="", sudo_salt=None)
        server.encrypted_sudo_password = ""
        server.sudo_salt = None
        _invalidate_server_pool(server)
    except Exception as exc:  # noqa: BLE001
        logger.warning("legacy sudo secret promote failed for server_id={}: {}", server.pk, exc)


def get_server_auth_secret(server, *, master_password: str = "", fallback_plain: str = "") -> str:
    managed_secret = get_managed_server_auth_secret(server.id)
    if managed_secret:
        return managed_secret
    direct = (fallback_plain or "").strip()
    if direct:
        return direct
    legacy = _decrypt_legacy_field(
        ciphertext=getattr(server, "encrypted_password", "") or "",
        salt=getattr(server, "salt", None),
        master_password=master_password,
        kind="auth",
        server_id=getattr(server, "pk", None),
    )
    if legacy:
        _promote_legacy_auth_secret(server, legacy)
        return legacy
    return ""


def get_server_sudo_secret(server, *, master_password: str = "", fallback_plain: str = "") -> str:
    managed_secret = get_managed_server_sudo_secret(server.id)
    if managed_secret:
        return managed_secret
    direct = (fallback_plain or "").strip()
    if direct:
        return direct
    legacy = _decrypt_legacy_field(
        ciphertext=getattr(server, "encrypted_sudo_password", "") or "",
        salt=getattr(server, "sudo_salt", None),
        master_password=master_password,
        kind="sudo",
        server_id=getattr(server, "pk", None),
    )
    if legacy:
        _promote_legacy_sudo_secret(server, legacy)
        return legacy
    return ""


def store_server_auth_secret(server, *, secret_value: str, master_password: str = "") -> None:
    if server.auth_method not in ("password", "key_password"):
        return
    secret = (secret_value or "").strip()
    set_managed_server_auth_secret(server.id, secret)
    server.salt = None
    server.encrypted_password = ""
    if getattr(server, "pk", None):
        from servers.models import Server

        Server.objects.filter(pk=server.pk).update(encrypted_password="", salt=None)
    _invalidate_server_pool(server)


def store_server_sudo_secret(server, *, secret_value: str, master_password: str = "") -> None:
    secret = (secret_value or "").strip()
    set_managed_server_sudo_secret(server.id, secret)
    server.sudo_salt = None
    server.encrypted_sudo_password = ""
    if getattr(server, "pk", None):
        from servers.models import Server

        Server.objects.filter(pk=server.pk).update(encrypted_sudo_password="", sudo_salt=None)
    _invalidate_server_pool(server)


def clear_server_auth_secret(server) -> None:
    set_managed_server_auth_secret(server.id, "")
    server.salt = None
    server.encrypted_password = ""
    if getattr(server, "pk", None):
        from servers.models import Server

        Server.objects.filter(pk=server.pk).update(encrypted_password="", salt=None)
    _invalidate_server_pool(server)


def clear_server_sudo_secret(server) -> None:
    set_managed_server_sudo_secret(server.id, "")
    server.sudo_salt = None
    server.encrypted_sudo_password = ""
    if getattr(server, "pk", None):
        from servers.models import Server

        Server.objects.filter(pk=server.pk).update(encrypted_sudo_password="", sudo_salt=None)
    _invalidate_server_pool(server)
