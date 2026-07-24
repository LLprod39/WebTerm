"""Fail-closed static policy for Ansible controller-side execution.

This policy is defense in depth, not a replacement for an isolated execution
environment.  It rejects constructs that can execute on, read from, or make
network requests from the Ansible control node before syntax-check or run.
"""

from __future__ import annotations

import ipaddress
import re
from collections.abc import Mapping
from pathlib import PurePosixPath
from typing import Any

_SAFE_DATA_LOOKUPS = frozenset(
    {
        "dict",
        "flattened",
        "indexed_items",
        "items",
        "list",
        "nested",
        "sequence",
        "subelements",
        "together",
    }
)
_SAFE_WITH_ITERATORS = frozenset(
    {
        "with_dict",
        "with_flattened",
        "with_indexed_items",
        "with_items",
        "with_list",
        "with_nested",
        "with_random_choice",
        "with_sequence",
        "with_subelements",
        "with_together",
    }
)
_CONTROLLER_FILE_MODULE_FIELDS = {
    "copy": ("src",),
    "fetch": ("dest",),
    "import_tasks": ("file",),
    "include_tasks": ("file",),
    "include_vars": ("file", "dir"),
    "script": ("cmd",),
    "synchronize": ("src",),
    "template": ("src",),
    "unarchive": ("src",),
    "win_copy": ("src",),
    "win_template": ("src",),
}
_LOOKUP_START_RE = re.compile(r"\b(?:lookup|query|q)\s*\(", re.IGNORECASE)
_LITERAL_PLUGIN_RE = re.compile(r"\s*(['\"])([A-Za-z0-9_.-]+)\1\s*(?:,|\))")
_DRIVE_RE = re.compile(r"^[A-Za-z]:[/\\]")
_SCHEME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*://")
_JINJA_MARKERS = ("{{", "{%", "{#")


def analyze_playbook_controller_policy(plays: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Inspect an already safely parsed playbook document."""

    findings: list[dict[str, Any]] = []
    _scan_value(plays, "playbook", findings, check_hosts=True, scan_lookups=True)
    return _deduplicate(findings)


def analyze_project_files_controller_policy(
    project_files: Mapping[str, bytes],
    *,
    skip_paths: set[str] | frozenset[str] | None = None,
) -> list[dict[str, Any]]:
    """Inspect every UTF-8 project asset and all structured YAML documents."""

    import yaml

    findings: list[dict[str, Any]] = []
    skipped = {str(path) for path in (skip_paths or set())}
    for path in sorted(project_files):
        if path in skipped:
            continue
        content = project_files[path]
        if not isinstance(content, bytes):
            _add(
                findings,
                "controller_project_file_invalid",
                "Project assets must be immutable byte payloads",
                f"bundle.{path}",
            )
            continue
        try:
            text = content.decode("utf-8")
        except UnicodeDecodeError:
            continue
        file_path = f"bundle.{path}"
        _scan_lookup_text(text, file_path, findings)
        if PurePosixPath(path).suffix.casefold() not in {".yml", ".yaml", ".json", ".j2"}:
            continue
        try:
            document = yaml.safe_load(text)
        except yaml.YAMLError:
            # Bundle inspection owns YAML validity.  Keep this policy focused on
            # controller behavior and retain the raw Jinja lookup findings above.
            continue
        is_root_playbook = "/" not in path and path.casefold() not in {
            "requirements.yml",
            "requirements.yaml",
        }
        _scan_value(
            document,
            file_path,
            findings,
            check_hosts=is_root_playbook,
            scan_lookups=False,
        )
    return _deduplicate(findings)


def _scan_value(
    value: Any,
    path: str,
    findings: list[dict[str, Any]],
    *,
    check_hosts: bool,
    scan_lookups: bool,
) -> None:
    if isinstance(value, dict):
        for raw_key in sorted(value, key=str):
            child = value[raw_key]
            key = str(raw_key)
            normalized = key.casefold()
            child_path = f"{path}.{key}"
            if normalized in {"connection", "ansible_connection"}:
                _check_connection(child, child_path, findings)
            elif normalized == "delegate_to":
                _check_delegate(child, child_path, findings)
            elif normalized == "local_action":
                _add(
                    findings,
                    "controller_local_action_forbidden",
                    "local_action executes on the Ansible control node",
                    child_path,
                )
            elif normalized.startswith("with_") and normalized not in _SAFE_WITH_ITERATORS:
                _add(
                    findings,
                    "controller_iterator_forbidden",
                    f"Controller-side iterator '{normalized}' is not allowed",
                    child_path,
                )
            elif normalized == "hosts" and check_hosts:
                _check_hosts(child, child_path, findings)
            elif normalized in {"vars_files", "import_playbook"}:
                _check_path_values(child, child_path, findings)
            elif normalized == "roles":
                _check_role_values(child, child_path, findings)

            module = normalized.rsplit(".", 1)[-1]
            if module == "add_host":
                _add(
                    findings,
                    "controller_dynamic_inventory_forbidden",
                    "add_host can expand execution beyond the frozen WebTerm target set",
                    child_path,
                )
            if module in _CONTROLLER_FILE_MODULE_FIELDS and not (
                module in {"copy", "unarchive"} and _remote_source(child)
            ):
                _check_module_paths(module, child, child_path, findings)
            if module in {"include_role", "import_role"}:
                _check_role_values(child, child_path, findings)

            if scan_lookups:
                _scan_lookup_text(key, f"{path}.[key]", findings)
            _scan_value(
                child,
                child_path,
                findings,
                check_hosts=check_hosts,
                scan_lookups=scan_lookups,
            )
    elif isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            _scan_value(
                child,
                f"{path}[{index}]",
                findings,
                check_hosts=check_hosts,
                scan_lookups=scan_lookups,
            )
    elif scan_lookups and isinstance(value, str):
        _scan_lookup_text(value, path, findings)


def _check_connection(value: Any, path: str, findings: list[dict[str, Any]]) -> None:
    text = str(value or "").strip()
    normalized = text.casefold()
    if _is_dynamic(text):
        _add(
            findings,
            "controller_connection_dynamic",
            "Dynamic Ansible connection selection is not allowed",
            path,
        )
    elif normalized in {"local", "ansible.builtin.local"}:
        _add(
            findings,
            "controller_connection_forbidden",
            "The local connection plugin executes on the Ansible control node",
            path,
        )


def _check_delegate(value: Any, path: str, findings: list[dict[str, Any]]) -> None:
    text = str(value or "").strip()
    if not text or _is_dynamic(text):
        _add(
            findings,
            "controller_delegate_dynamic",
            "Dynamic delegation cannot be proven to stay off the control node",
            path,
        )
    elif _is_loopback_host(text):
        _add(
            findings,
            "controller_delegate_forbidden",
            "Delegation to localhost or a loopback address is not allowed",
            path,
        )
    else:
        _add(
            findings,
            "controller_delegate_unbound",
            "Delegation can escape the frozen WebTerm target set and is not allowed",
            path,
        )


def _check_hosts(value: Any, path: str, findings: list[dict[str, Any]]) -> None:
    values = value if isinstance(value, list) else [value]
    for item in values:
        text = str(item or "").strip()
        if _is_dynamic(text):
            _add(
                findings,
                "controller_hosts_dynamic",
                "Dynamic host patterns cannot be proven to exclude the control node",
                path,
            )
            continue
        tokens = [token for token in re.split(r"[,:&!()\s]+", text) if token]
        if _is_loopback_host(text) or any(_is_loopback_host(token) for token in tokens):
            _add(
                findings,
                "controller_hosts_forbidden",
                "Play host patterns cannot target localhost or loopback addresses",
                path,
            )


def _scan_lookup_text(text: str, path: str, findings: list[dict[str, Any]]) -> None:
    for start in _LOOKUP_START_RE.finditer(text):
        plugin_match = _LITERAL_PLUGIN_RE.match(text, start.end())
        if plugin_match is None:
            _add(
                findings,
                "controller_lookup_dynamic",
                "Dynamic lookup plugin selection is not allowed",
                path,
            )
            continue
        plugin = plugin_match.group(2).casefold().rsplit(".", 1)[-1]
        if plugin not in _SAFE_DATA_LOOKUPS:
            _add(
                findings,
                "controller_lookup_forbidden",
                f"Controller-side lookup plugin '{plugin}' is not allowed",
                path,
                details={"plugin": plugin},
            )


def _check_module_paths(module: str, payload: Any, path: str, findings: list[dict[str, Any]]) -> None:
    if isinstance(payload, str):
        candidate = payload.split(maxsplit=1)[0] if module == "script" else payload
        _check_path(candidate, path, findings)
        return
    if not isinstance(payload, dict):
        return
    for field in _CONTROLLER_FILE_MODULE_FIELDS[module]:
        if field in payload:
            candidate = payload[field]
            if module == "script" and isinstance(candidate, str):
                candidate = candidate.split(maxsplit=1)[0]
            _check_path(candidate, f"{path}.{field}", findings)


def _check_path_values(value: Any, path: str, findings: list[dict[str, Any]]) -> None:
    values = value if isinstance(value, list) else [value]
    for index, candidate in enumerate(values):
        _check_path(candidate, f"{path}[{index}]" if len(values) > 1 else path, findings)


def _check_role_values(value: Any, path: str, findings: list[dict[str, Any]]) -> None:
    values = value if isinstance(value, list) else [value]
    for index, candidate in enumerate(values):
        if isinstance(candidate, dict):
            candidate = candidate.get("role") or candidate.get("name")
        _check_path(candidate, f"{path}[{index}]" if len(values) > 1 else path, findings)


def _check_path(value: Any, path: str, findings: list[dict[str, Any]]) -> None:
    if not isinstance(value, str) or not value.strip():
        return
    text = value.strip()
    normalized = text.replace("\\", "/")
    unsafe = (
        _is_dynamic(text)
        or normalized.startswith(("/", "//", "~"))
        or bool(_DRIVE_RE.match(text))
        or bool(_SCHEME_RE.match(text))
        or ".." in PurePosixPath(normalized).parts
    )
    if unsafe:
        _add(
            findings,
            "controller_path_forbidden",
            "Controller-side file references must be static project-relative paths",
            path,
        )


def _remote_source(payload: Any) -> bool:
    if not isinstance(payload, dict):
        return False
    value = payload.get("remote_src")
    return value is True or str(value).casefold() in {"true", "yes", "1"}


def _is_dynamic(text: str) -> bool:
    return any(marker in text for marker in _JINJA_MARKERS)


def _is_loopback_host(raw: str) -> bool:
    value = raw.strip().casefold().strip("[]").rstrip(".")
    if value in {"localhost", "localhost.localdomain", "ip6-localhost"} or value.endswith(".localhost"):
        return True
    if re.fullmatch(r"127(?:\.\d{1,3}){0,3}", value):
        return True
    try:
        return ipaddress.ip_address(value).is_loopback
    except ValueError:
        return False


def _add(
    findings: list[dict[str, Any]],
    code: str,
    message: str,
    path: str,
    *,
    details: dict[str, Any] | None = None,
) -> None:
    item: dict[str, Any] = {"code": code, "severity": "error", "message": message, "path": path}
    if details:
        item["details"] = details
    findings.append(item)


def _deduplicate(findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    unique: dict[tuple[str, str, str], dict[str, Any]] = {}
    for item in findings:
        key = (str(item.get("path") or ""), str(item.get("code") or ""), str(item.get("message") or ""))
        unique[key] = item
    return [unique[key] for key in sorted(unique)]
