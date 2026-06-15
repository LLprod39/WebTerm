from __future__ import annotations

import fnmatch
import subprocess
from dataclasses import dataclass
from pathlib import Path


class MarsPolicyError(ValueError):
    pass


@dataclass(frozen=True)
class WorkspacePolicy:
    root: Path
    read_allow_roots: tuple[Path, ...]
    write_allow_roots: tuple[Path, ...]
    deny_globs: tuple[str, ...]


def _resolve_path(value: str | Path) -> Path:
    return Path(value).expanduser().resolve(strict=False)


def path_is_inside(path: str | Path, root: str | Path) -> bool:
    resolved_path = _resolve_path(path)
    resolved_root = _resolve_path(root)
    try:
        resolved_path.relative_to(resolved_root)
    except ValueError:
        return False
    return True


def _is_denied(path: Path, root: Path, deny_globs: list[str] | tuple[str, ...]) -> bool:
    try:
        rel = path.relative_to(root).as_posix()
    except ValueError:
        return True
    rel_parts = rel.split("/")
    for pattern in deny_globs:
        normalized = str(pattern or "").strip().replace("\\", "/")
        if not normalized:
            continue
        if fnmatch.fnmatch(rel, normalized):
            return True
        if normalized.endswith("/**"):
            prefix = normalized[:-3].strip("/")
            if prefix and (rel == prefix or rel.startswith(f"{prefix}/")):
                return True
        if "/" not in normalized and any(fnmatch.fnmatch(part, normalized) for part in rel_parts):
            return True
    return False


def validate_workspace_root(root_path: str) -> Path:
    raw_root = Path(root_path).expanduser()
    if not raw_root.is_absolute():
        raise MarsPolicyError("Workspace root must be an absolute path.")
    root = raw_root.resolve(strict=False)
    if not root.exists() or not root.is_dir():
        raise MarsPolicyError("Workspace root must be an existing directory.")

    result = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "--is-inside-work-tree"],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    if result.returncode != 0 or result.stdout.strip().lower() != "true":
        raise MarsPolicyError("Workspace root must be inside a git repository.")
    return root


def build_workspace_policy(
    *,
    root_path: str,
    read_allow_roots: list[str] | None = None,
    write_allow_roots: list[str] | None = None,
    deny_globs: list[str] | None = None,
) -> WorkspacePolicy:
    root = validate_workspace_root(root_path)
    raw_read = read_allow_roots or [str(root)]
    raw_write = write_allow_roots or [str(root)]
    resolved_read = tuple(_validate_allow_root(item, root, "read") for item in raw_read)
    resolved_write = tuple(_validate_allow_root(item, root, "write") for item in raw_write)
    return WorkspacePolicy(
        root=root,
        read_allow_roots=resolved_read,
        write_allow_roots=resolved_write,
        deny_globs=tuple(deny_globs or []),
    )


def _validate_allow_root(value: str, root: Path, mode: str) -> Path:
    candidate = _resolve_path(value)
    if not path_is_inside(candidate, root):
        raise MarsPolicyError(f"{mode} allow root must stay inside the workspace root.")
    if candidate.exists() and not candidate.is_dir():
        raise MarsPolicyError(f"{mode} allow root must be a directory.")
    return candidate


def validate_workspace_child(
    *,
    root_path: str,
    child_path: str,
    deny_globs: list[str] | tuple[str, ...],
    write: bool = False,
    read_allow_roots: list[str] | None = None,
    write_allow_roots: list[str] | None = None,
) -> Path:
    policy = build_workspace_policy(
        root_path=root_path,
        read_allow_roots=read_allow_roots,
        write_allow_roots=write_allow_roots,
        deny_globs=list(deny_globs),
    )
    child = _resolve_path(child_path)
    allowed_roots = policy.write_allow_roots if write else policy.read_allow_roots
    if not any(path_is_inside(child, allowed_root) for allowed_root in allowed_roots):
        raise MarsPolicyError("Path is outside allowed workspace roots.")
    if _is_denied(child, policy.root, policy.deny_globs):
        raise MarsPolicyError("Path is denied by the workspace policy.")
    return child


def git_status(root_path: str) -> str:
    root = validate_workspace_root(root_path)
    result = subprocess.run(
        ["git", "-C", str(root), "status", "--porcelain"],
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    if result.returncode != 0:
        raise MarsPolicyError((result.stderr or result.stdout or "Unable to read git status.").strip())
    return result.stdout
