from __future__ import annotations

from collections.abc import Callable
from typing import Any

ServerSecretProvider = Callable[..., str]

_server_auth_secret_provider: ServerSecretProvider | None = None
_server_sudo_secret_provider: ServerSecretProvider | None = None
_server_private_key_provider: ServerSecretProvider | None = None


def register_server_auth_secret_provider(provider: ServerSecretProvider | None) -> None:
    global _server_auth_secret_provider
    _server_auth_secret_provider = provider


def register_server_sudo_secret_provider(provider: ServerSecretProvider | None) -> None:
    global _server_sudo_secret_provider
    _server_sudo_secret_provider = provider


def register_server_private_key_provider(provider: ServerSecretProvider | None) -> None:
    global _server_private_key_provider
    _server_private_key_provider = provider


def get_server_auth_secret(server: Any, *, master_password: str = "", fallback_plain: str = "") -> str:
    if _server_auth_secret_provider is None:
        return fallback_plain or ""
    return str(
        _server_auth_secret_provider(
            server,
            master_password=master_password,
            fallback_plain=fallback_plain,
        )
        or ""
    )


def get_server_sudo_secret(server: Any, *, master_password: str = "", fallback_plain: str = "") -> str:
    if _server_sudo_secret_provider is None:
        return fallback_plain or ""
    return str(
        _server_sudo_secret_provider(
            server,
            master_password=master_password,
            fallback_plain=fallback_plain,
        )
        or ""
    )


def get_server_private_key(server: Any) -> str:
    if _server_private_key_provider is None:
        return ""
    return str(_server_private_key_provider(server) or "")
