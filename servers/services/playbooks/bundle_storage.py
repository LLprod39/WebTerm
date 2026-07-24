"""Replaceable artifact storage boundary for playbook project bundles."""

from __future__ import annotations

import os
from contextlib import suppress
from pathlib import Path, PurePosixPath
from typing import Protocol
from uuid import uuid4

from django.conf import settings


class BundleStorageError(RuntimeError):
    """Artifact storage failed without exposing a filesystem path to API clients."""


class PlaybookBundleStorage(Protocol):
    def save(self, content: bytes, *, content_hash: str) -> str: ...

    def read(self, storage_key: str, *, max_bytes: int) -> bytes: ...

    def delete(self, storage_key: str) -> None: ...


class MediaRootPlaybookBundleStorage:
    """Single-node private storage for playbook project bundles.

    The interface is intentionally small so an object-storage backend can be
    substituted without changing bundle validation or ORM services.
    """

    def __init__(self, root: str | Path | None = None) -> None:
        configured = root or getattr(settings, "PLAYBOOK_BUNDLE_STORAGE_ROOT", None)
        self.root = Path(configured) if configured else Path(settings.BASE_DIR) / "private" / "playbook_bundles"
        if not settings.DEBUG and path_is_within(self.root, settings.MEDIA_ROOT):
            raise BundleStorageError("Playbook bundle storage must be outside MEDIA_ROOT in production")

    def save(self, content: bytes, *, content_hash: str) -> str:
        if not isinstance(content, bytes):
            raise BundleStorageError("Bundle artifact must be bytes")
        safe_hash = (
            content_hash
            if len(content_hash) == 64 and all(char in "0123456789abcdef" for char in content_hash)
            else "unknown"
        )
        storage_key = f"{safe_hash[:2]}/{uuid4().hex}.zip"
        target = self._resolve(storage_key, must_exist=False)
        target.parent.mkdir(parents=True, exist_ok=True)
        with suppress(OSError):
            os.chmod(target.parent, 0o700)
        temporary = target.with_name(f".{target.name}.{uuid4().hex}.tmp")
        try:
            with temporary.open("xb") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            with suppress(OSError):
                os.chmod(temporary, 0o600)
            os.replace(temporary, target)
        except OSError as exc:
            with suppress(OSError):
                temporary.unlink(missing_ok=True)
            raise BundleStorageError("Unable to store playbook bundle") from exc
        return storage_key

    def read(self, storage_key: str, *, max_bytes: int) -> bytes:
        target = self._resolve(storage_key, must_exist=True)
        try:
            if target.is_symlink() or not target.is_file():
                raise BundleStorageError("Playbook bundle artifact is not a regular file")
            if target.stat().st_size > max_bytes:
                raise BundleStorageError("Stored playbook bundle exceeds the read limit")
            with target.open("rb") as handle:
                content = handle.read(max_bytes + 1)
        except BundleStorageError:
            raise
        except OSError as exc:
            raise BundleStorageError("Unable to read playbook bundle") from exc
        if len(content) > max_bytes:
            raise BundleStorageError("Stored playbook bundle exceeds the read limit")
        return content

    def delete(self, storage_key: str) -> None:
        try:
            target = self._resolve(storage_key, must_exist=False)
            if target.exists() and not target.is_symlink():
                target.unlink()
        except (BundleStorageError, OSError):
            return

    def _resolve(self, storage_key: str, *, must_exist: bool) -> Path:
        if not isinstance(storage_key, str) or not storage_key or "\\" in storage_key:
            raise BundleStorageError("Invalid playbook bundle storage key")
        pure = PurePosixPath(storage_key)
        if pure.is_absolute() or any(part in {"", ".", ".."} for part in pure.parts):
            raise BundleStorageError("Invalid playbook bundle storage key")
        root = self.root.resolve()
        try:
            candidate = (root / Path(*pure.parts)).resolve(strict=must_exist)
        except OSError as exc:
            raise BundleStorageError("Playbook bundle artifact does not exist") from exc
        try:
            candidate.relative_to(root)
        except ValueError as exc:
            raise BundleStorageError("Playbook bundle storage key escapes its root") from exc
        return candidate


def get_playbook_bundle_storage() -> PlaybookBundleStorage:
    return MediaRootPlaybookBundleStorage()


def path_is_within(candidate: str | Path, root: str | Path) -> bool:
    """Return whether candidate resolves to root or one of its descendants."""

    try:
        Path(candidate).expanduser().resolve(strict=False).relative_to(Path(root).expanduser().resolve(strict=False))
    except (OSError, RuntimeError, ValueError):
        return False
    return True
