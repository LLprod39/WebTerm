from __future__ import annotations

import os
import secrets
from pathlib import Path

import asyncssh
from django.conf import settings


MAX_INLINE_PRIVATE_KEY_BYTES = 256 * 1024


def _keys_root() -> Path:
    return Path(getattr(settings, "SSH_PRIVATE_KEYS_DIR", Path(settings.BASE_DIR) / "data" / "ssh_keys")).resolve()


def _normalize_private_key(raw_value: str) -> str:
    key_text = (raw_value or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if not key_text:
        raise ValueError("SSH ключ пустой")
    if len(key_text.encode("utf-8")) > MAX_INLINE_PRIVATE_KEY_BYTES:
        raise ValueError("SSH ключ слишком большой")
    if "PRIVATE KEY" not in key_text:
        raise ValueError("Это не похоже на приватный SSH ключ")
    return f"{key_text}\n"


def _validate_private_key(key_text: str, *, passphrase: str = "") -> None:
    try:
        asyncssh.import_private_key(key_text, passphrase=passphrase or None)
    except Exception as exc:
        message = str(exc) or "Неверный приватный SSH ключ"
        raise ValueError(f"Неверный приватный SSH ключ: {message}") from exc


def _managed_key_path(user_id: int, server_id: int) -> Path:
    return _keys_root() / f"user-{user_id}" / f"server-{server_id}-{secrets.token_hex(8)}.key"


def is_managed_private_key_path(raw_path: str) -> bool:
    if not raw_path:
        return False
    try:
        path = Path(raw_path).expanduser().resolve()
        path.relative_to(_keys_root())
        return True
    except (OSError, ValueError):
        return False


def delete_managed_private_key(raw_path: str) -> None:
    if not is_managed_private_key_path(raw_path):
        return
    try:
        Path(raw_path).unlink(missing_ok=True)
    except OSError:
        return


def store_uploaded_private_key(server, raw_value: str, *, passphrase: str = "") -> str:
    key_text = _normalize_private_key(raw_value)
    _validate_private_key(key_text, passphrase=passphrase)

    target = _managed_key_path(server.user_id, server.id)
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(target.parent, 0o700)
    except OSError:
        pass

    tmp_target = target.with_suffix(".tmp")
    tmp_target.write_text(key_text, encoding="utf-8", newline="\n")
    try:
        os.chmod(tmp_target, 0o600)
    except OSError:
        pass
    tmp_target.replace(target)
    try:
        os.chmod(target, 0o600)
    except OSError:
        pass

    return str(target)
