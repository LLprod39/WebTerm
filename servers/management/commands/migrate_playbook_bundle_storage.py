from __future__ import annotations

import hashlib
import os
from contextlib import suppress
from pathlib import Path, PurePosixPath
from uuid import uuid4

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from servers.models import PlaybookAssetBundle
from servers.services.playbooks.bundle_storage import MediaRootPlaybookBundleStorage


class Command(BaseCommand):
    help = (
        "Copy legacy playbook bundle files out of MEDIA_ROOT, verify byte identity, "
        "and leave every source file untouched."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--source-root",
            default="",
            help="Legacy bundle root (defaults to MEDIA_ROOT/playbook_bundles)",
        )
        parser.add_argument(
            "--verify-only",
            action="store_true",
            help="Verify existing target copies without creating missing files",
        )

    def handle(self, *args, **options):
        source_root = Path(options["source_root"] or Path(settings.MEDIA_ROOT) / "playbook_bundles").resolve(
            strict=False
        )
        target_root = MediaRootPlaybookBundleStorage().root.resolve(strict=False)
        if source_root == target_root:
            raise CommandError("Legacy and private playbook bundle roots must be different")

        counts = {"copied": 0, "verified": 0, "target_only": 0}
        for bundle in PlaybookAssetBundle.objects.only("id", "storage_key").iterator(chunk_size=200):
            try:
                outcome = _copy_or_verify(
                    source_root=source_root,
                    target_root=target_root,
                    storage_key=bundle.storage_key,
                    verify_only=bool(options["verify_only"]),
                )
            except (OSError, ValueError) as exc:
                raise CommandError(f"Playbook bundle {bundle.id} could not be migrated: {exc}") from exc
            counts[outcome] += 1

        mode = "verified" if options["verify_only"] else "copied and verified"
        self.stdout.write(
            self.style.SUCCESS(
                f"Playbook bundles {mode}: copied={counts['copied']}, "
                f"verified={counts['verified']}, target_only={counts['target_only']}. "
                "Legacy source files were not deleted."
            )
        )


def _copy_or_verify(
    *,
    source_root: Path,
    target_root: Path,
    storage_key: str,
    verify_only: bool,
) -> str:
    source = _resolve_key(source_root, storage_key)
    target = _resolve_key(target_root, storage_key)
    source_exists = source.exists()
    target_exists = target.exists()

    if not source_exists:
        if not target_exists:
            raise ValueError("artifact is missing from both legacy and private storage")
        _file_digest(target)
        return "target_only"

    source_digest = _file_digest(source)
    if target_exists:
        if _file_digest(target) != source_digest or _file_digest(source) != source_digest:
            raise ValueError("private copy differs from the legacy source; refusing to overwrite it")
        return "verified"
    if verify_only:
        raise ValueError("private copy is missing")

    target.parent.mkdir(parents=True, exist_ok=True)
    with suppress(OSError):
        os.chmod(target.parent, 0o700)
    temporary = target.with_name(f".{target.name}.{uuid4().hex}.tmp")
    try:
        with source.open("rb") as source_handle, temporary.open("xb") as target_handle:
            while chunk := source_handle.read(1024 * 1024):
                target_handle.write(chunk)
            target_handle.flush()
            os.fsync(target_handle.fileno())
        with suppress(OSError):
            os.chmod(temporary, 0o600)
        try:
            os.link(temporary, target)
        except FileExistsError:
            if _file_digest(target) != source_digest:
                raise ValueError("private copy appeared concurrently with different bytes") from None
        final_source_digest = _file_digest(source)
        if final_source_digest != source_digest or _file_digest(target) != final_source_digest:
            raise ValueError("private copy failed byte-for-byte verification")
    finally:
        with suppress(OSError):
            temporary.unlink(missing_ok=True)
    return "copied"


def _resolve_key(root: Path, storage_key: str) -> Path:
    if not isinstance(storage_key, str) or not storage_key or "\\" in storage_key:
        raise ValueError("invalid storage key")
    pure = PurePosixPath(storage_key)
    if pure.is_absolute() or any(part in {"", ".", ".."} for part in pure.parts):
        raise ValueError("invalid storage key")
    candidate = (root / Path(*pure.parts)).resolve(strict=False)
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise ValueError("storage key escapes its root") from exc
    return candidate


def _file_digest(path: Path) -> tuple[int, str]:
    if path.is_symlink() or not path.is_file():
        raise ValueError("artifact is not a regular file")
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            size += len(chunk)
            digest.update(chunk)
    return size, digest.hexdigest()
