"""Canonical content helpers shared by drafts, revisions and migration checks."""

from __future__ import annotations

import hashlib
import json
from typing import Any

MAX_YAML_BYTES = 200_000
MAX_TASKS = 500
MAX_TASK_COMMAND_BYTES = 32_000


class PlaybookContentError(ValueError):
    """Raised when editable content cannot be stored safely."""


def content_format_for(*, kind: str, source_yaml: str) -> str:
    return "ansible_yaml" if kind == "ansible" or source_yaml else "runbook_json"


def normalize_tasks(raw: Any) -> list[dict[str, Any]]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise PlaybookContentError("tasks must be a list")
    if len(raw) > MAX_TASKS:
        raise PlaybookContentError(f"tasks cannot contain more than {MAX_TASKS} items")

    normalized: list[dict[str, Any]] = []
    for index, item in enumerate(raw):
        if not isinstance(item, dict):
            raise PlaybookContentError(f"task {index + 1} must be an object")
        command = str(item.get("command") or "")
        if len(command.encode("utf-8")) > MAX_TASK_COMMAND_BYTES:
            raise PlaybookContentError(f"task {index + 1} command is too large")
        normalized.append(
            {
                "id": str(item.get("id") or f"task_{index + 1}"),
                "command": command,
                "description": str(item.get("description") or ""),
                "continue_on_error": bool(
                    item.get("continue_on_error") if "continue_on_error" in item else item.get("continueOnError", False)
                ),
            }
        )
    return normalized


def validate_content(*, content_format: str, source_yaml: str, tasks: Any) -> tuple[str, list[dict[str, Any]]]:
    if content_format not in {"ansible_yaml", "runbook_json"}:
        raise PlaybookContentError("Unsupported playbook content format")
    source_yaml = source_yaml if isinstance(source_yaml, str) else str(source_yaml or "")
    if len(source_yaml.encode("utf-8")) > MAX_YAML_BYTES:
        raise PlaybookContentError(f"YAML cannot exceed {MAX_YAML_BYTES} bytes")
    normalized_tasks = normalize_tasks(tasks)
    if content_format == "ansible_yaml" and not source_yaml.strip():
        raise PlaybookContentError("Ansible YAML cannot be empty")
    if content_format == "runbook_json" and not normalized_tasks:
        raise PlaybookContentError("Runbook must contain at least one task")
    return source_yaml, normalized_tasks


def calculate_content_hash(
    *,
    content_format: str,
    source_yaml: str,
    tasks: Any,
    bundle_hash: str = "",
) -> str:
    payload = {
        "content_format": content_format,
        "source_yaml": source_yaml if isinstance(source_yaml, str) else str(source_yaml or ""),
        "tasks": tasks if isinstance(tasks, list) else [],
        "bundle_hash": bundle_hash or "",
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
