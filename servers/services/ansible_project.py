"""Safely materialize an already-inspected Ansible project for execution."""

from __future__ import annotations

import os
import re
from collections.abc import Mapping
from contextlib import suppress
from pathlib import Path, PurePosixPath


class AnsibleProjectError(ValueError):
    """A project path or payload violates the runtime materialization contract."""


_RUNTIME_RESERVED = frozenset(
    {"ansible.cfg", "extra_vars.json", "inventory.ini", "known_hosts"}
)
_RUNTIME_KEY_RE = re.compile(r"key_[0-9]+", re.IGNORECASE)


def is_runtime_reserved_path(raw_path: str) -> bool:
    """Return whether a root-relative path collides with runner-owned secrets."""

    if not isinstance(raw_path, str):
        return False
    normalized = raw_path.strip().replace("\\", "/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    normalized = normalized.rstrip("/")
    if not normalized or "/" in normalized:
        return False
    return normalized.casefold() in _RUNTIME_RESERVED or bool(
        _RUNTIME_KEY_RE.fullmatch(normalized)
    )


def _safe_relative_path(raw_path: str) -> PurePosixPath:
    if not isinstance(raw_path, str) or not raw_path or "\\" in raw_path or "\x00" in raw_path:
        raise AnsibleProjectError("Ansible project contains an invalid path")
    path = PurePosixPath(raw_path)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise AnsibleProjectError("Ansible project path escapes its workspace")
    if is_runtime_reserved_path(raw_path):
        raise AnsibleProjectError("Ansible project collides with a runtime-owned file")
    return path


def materialize_ansible_project(
    workdir: Path,
    *,
    playbook_yaml: str,
    project_files: Mapping[str, bytes] | None = None,
    entrypoint: str = "playbook.yml",
) -> str:
    """Write bounded, validated project files below ``workdir`` and return the entrypoint."""

    root = workdir.resolve()
    selected = _safe_relative_path(entrypoint or "playbook.yml")
    files = project_files or {}
    for raw_path, content in files.items():
        relative = _safe_relative_path(raw_path)
        if not isinstance(content, bytes):
            raise AnsibleProjectError("Ansible project files must be binary payloads")
        target = (root / Path(*relative.parts)).resolve()
        try:
            target.relative_to(root)
        except ValueError as exc:
            raise AnsibleProjectError("Ansible project path escapes its workspace") from exc
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        with suppress(OSError):
            os.chmod(target, 0o600)

    target = (root / Path(*selected.parts)).resolve()
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise AnsibleProjectError("Ansible entrypoint escapes its workspace") from exc
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(playbook_yaml, encoding="utf-8")
    with suppress(OSError):
        os.chmod(target, 0o600)
    return selected.as_posix()
