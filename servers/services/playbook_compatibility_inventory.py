"""Inventory binding compiler for imported Ansible playbooks."""

from __future__ import annotations

import hashlib
import re
from typing import Any

from servers.services.playbook_compatibility_analysis import _HOST_TOKEN_RE


def normalize_inventory_bindings(raw: Any) -> dict[str, dict[str, list[int]]]:
    if not isinstance(raw, dict):
        return {}
    normalized: dict[str, dict[str, list[int]]] = {}
    for selector, value in raw.items():
        if not isinstance(value, dict):
            continue
        server_ids = sorted({int(item) for item in value.get("server_ids") or [] if str(item).isdigit()})
        group_ids = sorted({int(item) for item in value.get("group_ids") or [] if str(item).isdigit()})
        normalized[str(selector)] = {"server_ids": server_ids, "group_ids": group_ids}
    return normalized


def safe_binding_group(selector: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_]", "_", selector).strip("_") or "target"
    if cleaned[0].isdigit():
        cleaned = f"target_{cleaned}"
    digest = hashlib.sha256(selector.encode("utf-8")).hexdigest()[:8]
    return f"wt_{cleaned[:36]}_{digest}"


def compile_runtime_playbook_yaml(
    source_yaml: str,
    resolved_bindings: dict[str, list[int]],
) -> tuple[str, dict[str, list[int]]]:
    """Rewrite only runtime host patterns to generated inventory groups."""
    if not resolved_bindings:
        return source_yaml, {}
    try:
        import yaml  # type: ignore

        document = yaml.safe_load(source_yaml)
    except Exception as exc:
        raise ValueError(f"Cannot compile runtime playbook: {exc}") from exc
    plays = document if isinstance(document, list) else [document]
    groups = {safe_binding_group(selector): ids for selector, ids in resolved_bindings.items() if ids}
    replacements = {selector: safe_binding_group(selector) for selector in resolved_bindings}

    def replace_pattern(value: Any) -> Any:
        if isinstance(value, list):
            return [replace_pattern(item) for item in value]
        text = str(value or "")
        return _HOST_TOKEN_RE.sub(lambda match: replacements.get(match.group(0), match.group(0)), text)

    for play in plays:
        if isinstance(play, dict) and "hosts" in play:
            play["hosts"] = replace_pattern(play["hosts"])
    runtime = yaml.safe_dump(plays, allow_unicode=True, sort_keys=False, default_flow_style=False)
    return runtime, groups


def inventory_groups_from_bindings(
    resolved_bindings: dict[str, list[int]],
) -> dict[str, list[int]]:
    return {safe_binding_group(selector): ids for selector, ids in resolved_bindings.items() if ids}
