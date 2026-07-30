from __future__ import annotations

import difflib
import json
from typing import Any

from app.egress_redaction import redact_egress_payload
from app.shell_commands import is_read_only_command

CHANGE_PREVIEW_SCHEMA_VERSION = "webterm.change-preview.v1"
_MAX_TEXT_CHARS = 4000
_MAX_DIFF_CHARS = 12000
_MAX_LIST_ITEMS = 100


def _bounded(value: Any, *, depth: int = 0) -> Any:
    if depth >= 6:
        return "[truncated:depth]"
    if isinstance(value, dict):
        return {str(key): _bounded(item, depth=depth + 1) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        items = [_bounded(item, depth=depth + 1) for item in value[:_MAX_LIST_ITEMS]]
        if len(value) > _MAX_LIST_ITEMS:
            items.append(f"[truncated:{len(value) - _MAX_LIST_ITEMS} items]")
        return items
    if isinstance(value, str) and len(value) > _MAX_TEXT_CHARS:
        return value[:_MAX_TEXT_CHARS].rstrip() + f"\n[truncated:{len(value) - _MAX_TEXT_CHARS} chars]"
    return value


def _safe(value: Any) -> Any:
    redacted, _report, _hashes = redact_egress_payload(_bounded(value))
    return redacted


def _diff_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, default=str)


def build_change_preview(
    *,
    operation: str,
    target: Any,
    before: Any,
    after: Any,
    dry_run: bool,
) -> dict[str, Any]:
    safe_target = _safe(target)
    safe_before = _safe(before)
    safe_after = _safe(after)
    before_text = _diff_text(safe_before)
    after_text = _diff_text(safe_after)
    diff = "\n".join(
        difflib.unified_diff(
            before_text.splitlines(),
            after_text.splitlines(),
            fromfile="before",
            tofile="planned" if dry_run else "after",
            lineterm="",
        )
    )
    if not diff:
        diff = "(no observable change)"
    if len(diff) > _MAX_DIFF_CHARS:
        diff = diff[:_MAX_DIFF_CHARS].rstrip() + f"\n[truncated:{len(diff) - _MAX_DIFF_CHARS} chars]"
    return {
        "schema_version": CHANGE_PREVIEW_SCHEMA_VERSION,
        "operation": str(operation),
        "target": safe_target,
        "dry_run": bool(dry_run),
        "changed": before_text != after_text,
        "before": safe_before,
        "after": safe_after,
        "diff": diff,
    }


def node_requires_change_preview(node_type: str, config: dict[str, Any]) -> bool:
    action = str(config.get("action") or "").strip().lower()
    if node_type == "agent/ssh_cmd":
        command = str(config.get("command") or "").strip()
        return bool(command) and not is_read_only_command(command)
    if node_type == "ops/file_action":
        return action == "write"
    if node_type == "ops/package_action":
        return action in {"install", "update", "remove"}
    if node_type == "ops/disk_cleanup":
        return action in {"journal_vacuum", "tmp_cleanup"}
    return node_type in {
        "ops/service_action",
        "ops/docker_action",
        "ops/process_action",
        "ops/alert_update",
    }


def valid_change_preview(value: Any) -> bool:
    return (
        isinstance(value, dict)
        and value.get("schema_version") == CHANGE_PREVIEW_SCHEMA_VERSION
        and isinstance(value.get("diff"), str)
        and bool(value.get("diff"))
        and isinstance(value.get("dry_run"), bool)
    )
