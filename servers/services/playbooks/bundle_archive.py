"""Untrusted Ansible project archive inspection and canonicalization.

Archive members are never extracted to caller-controlled paths.  Every member
is normalized, validated, size-bounded and read into memory before a canonical
ZIP with fixed permissions can be persisted.
"""

from __future__ import annotations

import hashlib
import re
import stat
import tarfile
import zipfile
from dataclasses import dataclass
from io import BytesIO
from pathlib import PurePosixPath
from typing import Any, BinaryIO

from django.conf import settings

DEFAULT_MAX_ARCHIVE_BYTES = 10 * 1024 * 1024
DEFAULT_MAX_FILE_BYTES = 2 * 1024 * 1024
DEFAULT_MAX_TOTAL_BYTES = 20 * 1024 * 1024
DEFAULT_MAX_FILES = 250
DEFAULT_MAX_YAML_ALIASES = 50

TEXT_EXTENSIONS = frozenset(
    {
        ".cfg",
        ".conf",
        ".ini",
        ".j2",
        ".json",
        ".md",
        ".ps1",
        ".py",
        ".service",
        ".sh",
        ".socket",
        ".timer",
        ".toml",
        ".txt",
        ".xml",
        ".yaml",
        ".yml",
    }
)
BINARY_EXTENSIONS = frozenset({".bin", ".gif", ".ico", ".jpeg", ".jpg", ".png", ".ttf", ".webp", ".woff", ".woff2"})
ALLOWED_EXTENSIONS = TEXT_EXTENSIONS | BINARY_EXTENSIONS
ALLOWED_TOP_LEVEL_DIRS = frozenset({"files", "group_vars", "roles", "templates", "vars"})
ALLOWED_ROLE_DIRS = frozenset({"defaults", "files", "handlers", "meta", "tasks", "templates", "vars"})
YAML_EXTENSIONS = frozenset({".yml", ".yaml"})

MANIFEST_NAME = "manifest.json"
MANIFEST_KIND = "webterm.playbook.bundle"
MANIFEST_SCHEMA_VERSION = 1
_DRIVE_PATH_RE = re.compile(r"^[A-Za-z]:")
_ROLE_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,99}$")
_WINDOWS_RESERVED = frozenset(
    {"aux", "con", "nul", "prn", *(f"com{i}" for i in range(1, 10)), *(f"lpt{i}" for i in range(1, 10))}
)


class BundleValidationError(ValueError):
    """A stable, non-secret archive validation failure."""

    def __init__(
        self,
        message: str,
        *,
        code: str = "invalid_bundle",
        status_code: int = 400,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.status_code = status_code
        self.details = details or {}


@dataclass(frozen=True)
class BundleLimits:
    max_archive_bytes: int = DEFAULT_MAX_ARCHIVE_BYTES
    max_file_bytes: int = DEFAULT_MAX_FILE_BYTES
    max_total_bytes: int = DEFAULT_MAX_TOTAL_BYTES
    max_files: int = DEFAULT_MAX_FILES
    max_yaml_aliases: int = DEFAULT_MAX_YAML_ALIASES

    @classmethod
    def from_settings(cls) -> BundleLimits:
        return cls(
            max_archive_bytes=_positive_setting("PLAYBOOK_BUNDLE_MAX_ARCHIVE_BYTES", DEFAULT_MAX_ARCHIVE_BYTES),
            max_file_bytes=_positive_setting("PLAYBOOK_BUNDLE_MAX_FILE_BYTES", DEFAULT_MAX_FILE_BYTES),
            max_total_bytes=_positive_setting("PLAYBOOK_BUNDLE_MAX_TOTAL_BYTES", DEFAULT_MAX_TOTAL_BYTES),
            max_files=_positive_setting("PLAYBOOK_BUNDLE_MAX_FILES", DEFAULT_MAX_FILES),
            max_yaml_aliases=_positive_setting("PLAYBOOK_BUNDLE_MAX_YAML_ALIASES", DEFAULT_MAX_YAML_ALIASES),
        )


@dataclass(frozen=True)
class BundleFile:
    path: str
    content: bytes
    sha256: str
    is_text: bool

    def manifest_item(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "size_bytes": len(self.content),
            "sha256": self.sha256,
            "is_text": self.is_text,
        }


@dataclass(frozen=True)
class InspectedBundle:
    archive_format: str
    files: tuple[BundleFile, ...]
    content_hash: str
    total_size: int
    manifest: dict[str, Any]
    entrypoints: tuple[dict[str, Any], ...]
    secret_findings: tuple[dict[str, str], ...]

    def file_map(self) -> dict[str, BundleFile]:
        return {item.path: item for item in self.files}


def _positive_setting(name: str, default: int) -> int:
    try:
        value = int(getattr(settings, name, default))
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default


def read_archive_stream(stream: BinaryIO, *, limits: BundleLimits | None = None) -> bytes:
    """Read an upload without trusting its declared size."""

    limits = limits or BundleLimits.from_settings()
    declared_size = getattr(stream, "size", None)
    if isinstance(declared_size, int) and declared_size > limits.max_archive_bytes:
        raise _limit_error("Archive exceeds the upload size limit", "archive_size_limit")

    output = bytearray()
    chunks = stream.chunks() if callable(getattr(stream, "chunks", None)) else iter(lambda: stream.read(64 * 1024), b"")
    for chunk in chunks:
        if not isinstance(chunk, (bytes, bytearray)):
            raise BundleValidationError("Archive upload returned non-binary data", code="invalid_upload")
        output.extend(chunk)
        if len(output) > limits.max_archive_bytes:
            raise _limit_error("Archive exceeds the upload size limit", "archive_size_limit")
    if not output:
        raise BundleValidationError("Archive is empty", code="empty_archive")
    return bytes(output)


def inspect_project_bundle(
    data: bytes,
    *,
    limits: BundleLimits | None = None,
    allow_single_root: bool = False,
) -> InspectedBundle:
    from servers.services.playbooks.bundle_content import (
        build_entrypoint_previews,
        parse_manifest,
        safe_json_load,
        safe_yaml_load,
        scan_bundle_secrets,
        validate_requirements,
    )

    limits = limits or BundleLimits.from_settings()
    if not isinstance(data, bytes) or not data:
        raise BundleValidationError("Archive is empty", code="empty_archive")
    if len(data) > limits.max_archive_bytes:
        raise _limit_error("Archive exceeds the upload size limit", "archive_size_limit")

    stream = BytesIO(data)
    try:
        if zipfile.is_zipfile(stream):
            archive_format = "zip"
            files = _read_zip(data, limits, allow_single_root=allow_single_root)
        else:
            archive_format = "tar"
            files = _read_tar(data, limits, allow_single_root=allow_single_root)
    except BundleValidationError:
        raise
    except (OSError, tarfile.TarError, zipfile.BadZipFile, RuntimeError) as exc:
        raise BundleValidationError("Archive is malformed or unsupported", code="malformed_archive") from exc

    if not files:
        raise BundleValidationError("Archive contains no supported files", code="empty_archive")

    file_map = {item.path: item for item in files}
    manifest = parse_manifest(file_map.get(MANIFEST_NAME))
    yaml_documents: dict[str, Any] = {}
    json_documents: dict[str, Any] = {}
    for item in files:
        suffix = PurePosixPath(item.path).suffix.lower()
        if suffix in YAML_EXTENSIONS:
            yaml_documents[item.path] = safe_yaml_load(item.path, item.content, limits)
        elif suffix == ".json" and item.path != MANIFEST_NAME:
            json_documents[item.path] = safe_json_load(item.path, item.content)

    validate_requirements(yaml_documents)
    entrypoints = build_entrypoint_previews(yaml_documents)
    if not entrypoints:
        raise BundleValidationError(
            "Bundle must contain at least one root Ansible playbook",
            code="missing_entrypoint",
        )
    manifest_entrypoint = str(manifest.get("entrypoint") or "")
    if manifest_entrypoint and manifest_entrypoint not in {item["path"] for item in entrypoints}:
        raise BundleValidationError(
            "Manifest entrypoint is not a root Ansible playbook",
            code="invalid_manifest_entrypoint",
        )

    secret_findings = scan_bundle_secrets(files, yaml_documents, json_documents)
    return InspectedBundle(
        archive_format=archive_format,
        files=tuple(files),
        content_hash=calculate_bundle_content_hash({item.path: item.content for item in files}),
        total_size=sum(len(item.content) for item in files),
        manifest=manifest,
        entrypoints=tuple(entrypoints),
        secret_findings=tuple(secret_findings),
    )


def calculate_bundle_content_hash(files: dict[str, bytes]) -> str:
    digest = hashlib.sha256()
    for path in sorted(files):
        encoded_path = path.encode("utf-8")
        content = files[path]
        digest.update(len(encoded_path).to_bytes(4, "big"))
        digest.update(encoded_path)
        digest.update(len(content).to_bytes(8, "big"))
        digest.update(content)
    return digest.hexdigest()


def build_canonical_zip(files: dict[str, bytes]) -> bytes:
    output = BytesIO()
    with zipfile.ZipFile(output, mode="w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(files):
            normalized = normalize_bundle_path(path)
            _validate_file_layout(normalized)
            info = zipfile.ZipInfo(normalized, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = (stat.S_IFREG | 0o600) << 16
            archive.writestr(info, files[path])
    return output.getvalue()


def sanitize_file_for_export(item: BundleFile) -> tuple[bytes | None, int]:
    from servers.services.playbooks.bundle_content import sanitize_file_for_export as sanitize

    return sanitize(item)


def normalize_bundle_path(raw_name: str) -> str:
    if not isinstance(raw_name, str) or not raw_name or "\x00" in raw_name:
        raise BundleValidationError("Archive contains an invalid path", code="unsafe_path")
    if any(ord(char) < 32 for char in raw_name):
        raise BundleValidationError("Archive path contains control characters", code="unsafe_path")

    name = raw_name.replace("\\", "/").rstrip("/")
    if not name or name.startswith("/") or name.startswith("//") or _DRIVE_PATH_RE.match(name):
        raise BundleValidationError("Absolute archive paths are not allowed", code="unsafe_path")
    if ":" in name:
        raise BundleValidationError("Archive path contains a reserved separator", code="unsafe_path")
    parts = name.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise BundleValidationError("Archive path traversal is not allowed", code="unsafe_path")
    if any(part.startswith(".") for part in parts):
        raise BundleValidationError("Hidden archive paths are not allowed", code="unsafe_path")
    if any(len(part) > 120 for part in parts) or len(name) > 300:
        raise BundleValidationError("Archive path is too long", code="unsafe_path")
    if any(PurePosixPath(part).stem.casefold() in _WINDOWS_RESERVED for part in parts):
        raise BundleValidationError("Archive path uses a reserved filename", code="unsafe_path")
    return "/".join(parts)


def _read_zip(data: bytes, limits: BundleLimits, *, allow_single_root: bool = False) -> list[BundleFile]:
    files: list[BundleFile] = []
    seen: set[str] = set()
    total = 0
    with zipfile.ZipFile(BytesIO(data), mode="r") as archive:
        members = archive.infolist()
        if len(members) > limits.max_files:
            raise _limit_error("Archive contains too many files or directory members", "file_count_limit")
        normalized_paths = [normalize_bundle_path(info.filename) for info in members]
        root_prefix = _single_root_prefix(
            [path for info, path in zip(members, normalized_paths, strict=True) if not info.is_dir()]
        ) if allow_single_root else ""
        for info, normalized_path in zip(members, normalized_paths, strict=True):
            path = _strip_root_prefix(normalized_path, root_prefix)
            if not path and info.is_dir():
                continue
            if not path:
                raise BundleValidationError("Archive root contains an invalid file", code="unsafe_path")
            mode = (info.external_attr >> 16) & 0xFFFF
            file_type = stat.S_IFMT(mode)
            if file_type == stat.S_IFLNK:
                raise BundleValidationError("Archive symlinks are not allowed", code="unsafe_link")
            if file_type not in {0, stat.S_IFDIR, stat.S_IFREG}:
                raise BundleValidationError("Archive contains a non-regular file", code="unsafe_member")
            if info.flag_bits & 0x1:
                raise BundleValidationError("Encrypted archive members are not supported", code="encrypted_member")
            if info.is_dir():
                _validate_directory_layout(path)
                continue
            _validate_file_layout(path)
            _check_duplicate(path, seen)
            _check_declared_limits(info.file_size, len(files) + 1, total, limits)
            with archive.open(info, mode="r") as member:
                content = member.read(limits.max_file_bytes + 1)
            total = _check_actual_limits(content, len(files) + 1, total, limits)
            files.append(_bundle_file(path, content))
    return files


def _read_tar(data: bytes, limits: BundleLimits, *, allow_single_root: bool = False) -> list[BundleFile]:
    files: list[BundleFile] = []
    seen: set[str] = set()
    total = 0
    with tarfile.open(fileobj=BytesIO(data), mode="r:*") as archive:
        members = archive.getmembers()
        if len(members) > limits.max_files:
            raise _limit_error("Archive contains too many files or directory members", "file_count_limit")
        normalized_paths = [normalize_bundle_path(member.name) for member in members]
        root_prefix = _single_root_prefix(
            [path for member, path in zip(members, normalized_paths, strict=True) if member.isfile()]
        ) if allow_single_root else ""
        for member_count, (member, normalized_path) in enumerate(
            zip(members, normalized_paths, strict=True),
            start=1,
        ):
            if member_count > limits.max_files:
                raise _limit_error("Archive contains too many files or directory members", "file_count_limit")
            path = _strip_root_prefix(normalized_path, root_prefix)
            if not path and member.isdir():
                continue
            if not path:
                raise BundleValidationError("Archive root contains an invalid file", code="unsafe_path")
            if member.issym() or member.islnk():
                raise BundleValidationError("Archive links are not allowed", code="unsafe_link")
            if member.isdir():
                _validate_directory_layout(path)
                continue
            if not member.isfile() or getattr(member, "sparse", None):
                raise BundleValidationError("Archive contains a non-regular file", code="unsafe_member")
            _validate_file_layout(path)
            _check_duplicate(path, seen)
            _check_declared_limits(member.size, len(files) + 1, total, limits)
            source = archive.extractfile(member)
            if source is None:
                raise BundleValidationError("Archive member cannot be read", code="malformed_archive")
            content = source.read(limits.max_file_bytes + 1)
            total = _check_actual_limits(content, len(files) + 1, total, limits)
            files.append(_bundle_file(path, content))
    return files


def _single_root_prefix(file_paths: list[str]) -> str:
    """Return the wrapper directory used by provider-generated repository archives."""

    if not file_paths:
        return ""
    parts = [PurePosixPath(path).parts for path in file_paths]
    first = parts[0][0]
    if all(len(item) > 1 and item[0] == first for item in parts):
        return first
    return ""


def _strip_root_prefix(path: str, root_prefix: str) -> str:
    if not root_prefix:
        return path
    if path == root_prefix:
        return ""
    prefix = f"{root_prefix}/"
    return path[len(prefix):] if path.startswith(prefix) else path


def _bundle_file(path: str, content: bytes) -> BundleFile:
    suffix = PurePosixPath(path).suffix.lower()
    is_text = suffix in TEXT_EXTENSIONS
    if is_text:
        try:
            content.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise BundleValidationError(
                f"Text file is not valid UTF-8: {path}",
                code="invalid_text_encoding",
            ) from exc
    return BundleFile(path=path, content=content, sha256=hashlib.sha256(content).hexdigest(), is_text=is_text)


def _validate_directory_layout(path: str) -> None:
    parts = PurePosixPath(path).parts
    if not parts or parts[0] not in ALLOWED_TOP_LEVEL_DIRS:
        raise BundleValidationError("Archive contains a disallowed directory", code="disallowed_path")
    if parts[0] == "roles" and len(parts) >= 2 and not _ROLE_NAME_RE.fullmatch(parts[1]):
        raise BundleValidationError("Role name is invalid", code="disallowed_path")
    if parts[0] == "roles" and len(parts) >= 3 and parts[2] not in ALLOWED_ROLE_DIRS:
        raise BundleValidationError("Role directory is not allowlisted", code="disallowed_path")


def _validate_file_layout(path: str) -> None:
    parts = PurePosixPath(path).parts
    suffix = PurePosixPath(path).suffix.lower()
    if path == MANIFEST_NAME:
        return
    if suffix not in ALLOWED_EXTENSIONS:
        raise BundleValidationError(
            f"File extension is not allowlisted: {suffix or '[none]'}", code="disallowed_extension"
        )
    if len(parts) == 1:
        if suffix not in YAML_EXTENSIONS and suffix != ".md":
            raise BundleValidationError(
                "Only playbooks, requirements and README are allowed at bundle root", code="disallowed_path"
            )
        return
    if parts[0] not in ALLOWED_TOP_LEVEL_DIRS:
        raise BundleValidationError("Top-level bundle directory is not allowlisted", code="disallowed_path")
    if parts[0] == "roles":
        if len(parts) < 3 or not _ROLE_NAME_RE.fullmatch(parts[1]):
            raise BundleValidationError("Role file path is invalid", code="disallowed_path")
        if len(parts) == 3 and parts[2].casefold() == "readme.md":
            return
        if len(parts) < 4 or parts[2] not in ALLOWED_ROLE_DIRS:
            raise BundleValidationError("Role directory is not allowlisted", code="disallowed_path")
    if parts[0] in {"group_vars", "vars"} and suffix not in YAML_EXTENSIONS | {".json"}:
        raise BundleValidationError("Variable files must be YAML or JSON", code="disallowed_extension")
    if parts[0] == "templates" and suffix not in TEXT_EXTENSIONS:
        raise BundleValidationError("Templates must be UTF-8 text", code="disallowed_extension")


def _check_duplicate(path: str, seen: set[str]) -> None:
    canonical = path.casefold()
    if canonical in seen:
        raise BundleValidationError("Archive contains duplicate normalized paths", code="duplicate_path")
    seen.add(canonical)


def _check_declared_limits(size: int, count: int, total: int, limits: BundleLimits) -> None:
    if count > limits.max_files:
        raise _limit_error("Archive contains too many files", "file_count_limit")
    if size < 0 or size > limits.max_file_bytes:
        raise _limit_error("Archive member exceeds the per-file size limit", "file_size_limit")
    if total + size > limits.max_total_bytes:
        raise _limit_error("Archive exceeds the extracted size limit", "total_size_limit")


def _check_actual_limits(content: bytes, count: int, total: int, limits: BundleLimits) -> int:
    if len(content) > limits.max_file_bytes:
        raise _limit_error("Archive member exceeds the per-file size limit", "file_size_limit")
    next_total = total + len(content)
    if count > limits.max_files:
        raise _limit_error("Archive contains too many files", "file_count_limit")
    if next_total > limits.max_total_bytes:
        raise _limit_error("Archive exceeds the extracted size limit", "total_size_limit")
    return next_total


def _limit_error(message: str, code: str) -> BundleValidationError:
    return BundleValidationError(message, code=code, status_code=413)
