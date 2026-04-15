from __future__ import annotations

import os

from core_ui.managed_secrets import (
    get_server_auth_secret as get_managed_server_auth_secret,
)
from core_ui.managed_secrets import (
    has_server_auth_secret,
)
from core_ui.managed_secrets import (
    set_server_auth_secret as set_managed_server_auth_secret,
)
from passwords.encryption import PasswordEncryption


def has_saved_server_secret(server) -> bool:
    return bool(has_server_auth_secret(server.id) or server.encrypted_password)


def get_server_auth_secret(server, *, master_password: str = "", fallback_plain: str = "") -> str:
    managed_secret = get_managed_server_auth_secret(server.id)
    if managed_secret:
        return managed_secret

    if server.auth_method not in ("password", "key_password"):
        return ""

    if server.encrypted_password:
        resolved_master_password = (master_password or "").strip() or (os.environ.get("MASTER_PASSWORD") or "").strip()
        if not resolved_master_password:
            return fallback_plain or ""
        if not server.salt:
            raise ValueError("У сервера есть encrypted_password, но отсутствует salt — расшифровка невозможна")
        try:
            return PasswordEncryption.decrypt_password(
                server.encrypted_password,
                resolved_master_password,
                bytes(server.salt),
            )
        except Exception as exc:
            if fallback_plain:
                return fallback_plain
            msg = (str(exc) or "").strip() or "Неверный MASTER_PASSWORD или повреждённый секрет"
            raise ValueError(msg) from exc

    return fallback_plain or ""


def store_server_auth_secret(server, *, secret_value: str, master_password: str = "") -> None:
    if server.auth_method not in ("password", "key_password"):
        return
    secret = (secret_value or "").strip()
    if not secret:
        set_managed_server_auth_secret(server.id, "")
        server.salt = None
        server.encrypted_password = ""
        return

    set_managed_server_auth_secret(server.id, secret)
    if master_password:
        server.salt = PasswordEncryption.generate_salt()
        server.encrypted_password = PasswordEncryption.encrypt_password(
            secret,
            master_password,
            server.salt,
        )
    elif not server.encrypted_password:
        server.salt = None
        server.encrypted_password = ""


def clear_server_auth_secret(server) -> None:
    set_managed_server_auth_secret(server.id, "")
    server.salt = None
    server.encrypted_password = ""
