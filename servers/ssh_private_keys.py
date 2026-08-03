from __future__ import annotations

import contextlib
import getpass
import os
import subprocess
from pathlib import Path, PurePosixPath
from typing import Any

import asyncssh
from django.conf import settings

from core_ui.managed_secrets import (
    get_server_ssh_private_key,
    set_server_ssh_private_key,
)

MAX_INLINE_PRIVATE_KEY_BYTES = 256 * 1024
MANAGED_PRIVATE_KEY_REFERENCE_PREFIX = "managed://server-ssh-private-key/v1/"


class SSHPrivateKeyStorageError(RuntimeError):
    """Raised when a configured private key cannot be loaded safely."""


def _keys_root() -> Path:
    return Path(getattr(settings, "SSH_PRIVATE_KEYS_DIR", Path(settings.BASE_DIR) / "data" / "ssh_keys")).resolve()


def managed_private_keys_root() -> Path:
    return _keys_root()


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


def managed_private_key_reference(server_id: int) -> str:
    return f"{MANAGED_PRIVATE_KEY_REFERENCE_PREFIX}{int(server_id)}"


def is_managed_private_key_reference(raw_reference: str, *, server_id: int | None = None) -> bool:
    raw = str(raw_reference or "").strip()
    if not raw.startswith(MANAGED_PRIVATE_KEY_REFERENCE_PREFIX):
        return False
    object_id = raw.removeprefix(MANAGED_PRIVATE_KEY_REFERENCE_PREFIX)
    if not object_id.isdigit() or int(object_id) <= 0:
        return False
    return server_id is None or int(object_id) == int(server_id)


def is_managed_private_key_path(raw_path: str) -> bool:
    return resolve_managed_private_key_path(raw_path) is not None


def resolve_managed_private_key_path(raw_path: str) -> Path | None:
    """Resolve native and legacy container paths into the configured key root."""

    if not raw_path or is_managed_private_key_reference(raw_path):
        return None
    try:
        path = Path(raw_path).expanduser().resolve()
        path.relative_to(_keys_root())
        return path
    except (OSError, ValueError):
        pass

    posix_path = PurePosixPath(str(raw_path).replace("\\", "/"))
    legacy_root = PurePosixPath("/workspace/data/ssh_keys")
    try:
        relative = posix_path.relative_to(legacy_root)
    except ValueError:
        return None
    candidate = (_keys_root() / Path(*relative.parts)).resolve()
    try:
        candidate.relative_to(_keys_root())
    except ValueError:
        return None
    return candidate


def delete_managed_private_key(raw_path: str) -> None:
    """Delete only a legacy plaintext key file owned by WebTerm."""

    if not is_managed_private_key_path(raw_path):
        return
    try:
        path = resolve_managed_private_key_path(raw_path)
        if path is not None:
            path.unlink(missing_ok=True)
    except OSError:
        return


def store_uploaded_private_key(server: Any, raw_value: str, *, passphrase: str = "") -> str:
    """Validate and store an uploaded key in the encrypted Managed Secret store."""

    key_text = _normalize_private_key(raw_value)
    _validate_private_key(key_text, passphrase=passphrase)
    set_server_ssh_private_key(int(server.id), key_text)
    return managed_private_key_reference(int(server.id))


def get_server_private_key_text(server: Any) -> str:
    """Resolve a managed key or a legacy/operator-owned path into key text.

    New uploads always use ManagedSecret. Files remain readable only for a
    bounded migration/compatibility window and are never written by this path.
    """

    server_id = int(getattr(server, "id", 0) or 0)
    key_reference = str(getattr(server, "key_path", "") or "").strip()
    if not key_reference:
        return ""

    if key_reference.startswith(MANAGED_PRIVATE_KEY_REFERENCE_PREFIX):
        if not is_managed_private_key_reference(key_reference, server_id=server_id):
            raise SSHPrivateKeyStorageError("Managed SSH key reference does not belong to this server")
        key_text = get_server_ssh_private_key(server_id)
        if not key_text:
            raise SSHPrivateKeyStorageError("Managed SSH private key is missing")
        return _normalize_private_key(key_text)

    legacy_managed_path = resolve_managed_private_key_path(key_reference)
    source_path = legacy_managed_path or Path(key_reference).expanduser()
    try:
        key_text = source_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise SSHPrivateKeyStorageError("Configured SSH private key cannot be read") from exc
    return _normalize_private_key(key_text)


def import_server_private_key(
    server: Any,
    *,
    passphrase: str = "",
    private_key_text: str | None = None,
) -> asyncssh.SSHKey:
    key_text = private_key_text if private_key_text is not None else get_server_private_key_text(server)
    if not key_text:
        raise SSHPrivateKeyStorageError("SSH private key is not configured")
    try:
        return asyncssh.import_private_key(key_text, passphrase=passphrase or None)
    except Exception as exc:
        raise SSHPrivateKeyStorageError("Configured SSH private key cannot be unlocked") from exc


def _restrict_windows_acl(path: Path) -> None:
    account = getpass.getuser().strip()
    if not account:
        raise SSHPrivateKeyStorageError("Cannot determine the Windows service account for SSH key ACLs")
    result = subprocess.run(
        [
            "icacls.exe",
            str(path),
            "/inheritance:r",
            "/grant:r",
            f"{account}:(F)",
            "*S-1-5-18:(F)",
            "*S-1-5-32-544:(F)",
        ],
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    if result.returncode != 0:
        raise SSHPrivateKeyStorageError("Cannot restrict the temporary SSH private key ACL")


def write_ephemeral_private_key(path: Path, private_key_text: str) -> Path:
    """Write a short-lived runtime key with fail-closed OS permissions."""

    target = Path(path)
    key_text = _normalize_private_key(private_key_text)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(key_text)
        os.chmod(target, 0o600)
        if os.name == "nt":
            _restrict_windows_acl(target)
    except Exception:
        with contextlib.suppress(OSError):
            target.unlink()
        raise
    return target
