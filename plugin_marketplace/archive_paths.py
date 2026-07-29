from __future__ import annotations

from pathlib import Path, PurePosixPath, PureWindowsPath


class UnsafeArchivePathError(ValueError):
    pass


_WINDOWS_DEVICE_NAMES = {
    "AUX",
    "CON",
    "NUL",
    "PRN",
    *(f"COM{index}" for index in range(1, 10)),
    *(f"LPT{index}" for index in range(1, 10)),
}


def normalized_archive_member_parts(name: str) -> tuple[str, ...]:
    if not isinstance(name, str) or not name or "\x00" in name:
        raise UnsafeArchivePathError("archive member path is empty or contains a null byte")

    windows_path = PureWindowsPath(name)
    normalized = name.replace("\\", "/")
    posix_path = PurePosixPath(normalized)
    if windows_path.drive or windows_path.root or windows_path.is_absolute() or posix_path.is_absolute():
        raise UnsafeArchivePathError("archive member path is absolute or drive-qualified")

    parts = tuple(normalized.split("/"))
    if not parts or any(part in {"", ".", ".."} for part in parts):
        raise UnsafeArchivePathError("archive member path contains an ambiguous or parent component")
    for part in parts:
        if ":" in part or part != part.rstrip(" ."):
            raise UnsafeArchivePathError("archive member path is not a canonical Windows path")
        device_stem = part.split(".", 1)[0].upper()
        if device_stem in _WINDOWS_DEVICE_NAMES:
            raise UnsafeArchivePathError("archive member path uses a Windows device name")
    return parts


def is_safe_archive_member(name: str) -> bool:
    try:
        normalized_archive_member_parts(name)
    except UnsafeArchivePathError:
        return False
    return True


def archive_member_target(destination: Path, name: str) -> Path:
    parts = normalized_archive_member_parts(name)
    root = destination.resolve()
    target = root.joinpath(*parts).resolve()
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise UnsafeArchivePathError("archive member path escapes the destination") from exc
    return target
