from __future__ import annotations

import json
from typing import Any

from app.agent_kernel.memory.redaction import sanitize_prompt_context_text
from studio.pipeline.pipeline_secrets import redact_pipeline_secret_values


def _extract_json_object(raw_text: str) -> dict[str, Any]:
    text = (raw_text or "").strip()
    if not text:
        return {}
    text = text.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return {}
    try:
        parsed = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _prompt_json(value: object, *, limit: int) -> str:
    value = redact_pipeline_secret_values(value)
    try:
        serialized = json.dumps(value, ensure_ascii=False, indent=2)
    except TypeError:
        serialized = json.dumps(str(value), ensure_ascii=False)
    sanitized = sanitize_prompt_context_text(serialized).text.strip()
    return sanitized[:limit] if len(sanitized) > limit else sanitized


def _string_items(value: object, *, limit: int = 8) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()][:limit]


def _dict_items(value: object, *, limit: int = 12) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    result: list[dict[str, Any]] = []
    for item in value:
        if isinstance(item, dict):
            result.append(dict(item))
        elif str(item).strip():
            result.append({"name": str(item).strip()})
        if len(result) >= limit:
            break
    return result


def _compact_available_resources(assistant_context: dict[str, Any]) -> dict[str, Any]:
    def _pick(items: object, fields: tuple[str, ...], *, limit: int = 12) -> list[dict[str, Any]]:
        if not isinstance(items, list):
            return []
        result: list[dict[str, Any]] = []
        for item in items[:limit]:
            if not isinstance(item, dict):
                continue
            payload = {field: item.get(field) for field in fields if item.get(field) not in (None, "", [])}
            if payload:
                result.append(payload)
        return result

    capability_registry = assistant_context.get("capability_registry")
    task_families = []
    capability_packs = []
    if isinstance(capability_registry, dict):
        task_families = _pick(
            capability_registry.get("task_families"),
            ("slug", "name", "readiness", "missing"),
            limit=8,
        )
        packs = capability_registry.get("capability_packs")
        if isinstance(packs, list):
            for pack in packs[:8]:
                if not isinstance(pack, dict):
                    continue
                tools = pack.get("tools")
                capability_packs.append(
                    {
                        "slug": pack.get("slug"),
                        "service": pack.get("service"),
                        "mcp_server_name": pack.get("mcp_server_name"),
                        "tool_names": [
                            tool.get("tool_name")
                            for tool in tools[:8]
                            if isinstance(tool, dict) and tool.get("tool_name")
                        ]
                        if isinstance(tools, list)
                        else [],
                    }
                )

    return {
        "servers": _pick(assistant_context.get("available_servers"), ("id", "name", "host", "server_type")),
        "agents": _pick(assistant_context.get("available_agents"), ("id", "name", "description")),
        "mcp_servers": _pick(
            assistant_context.get("available_mcp_servers"),
            ("id", "name", "transport", "description", "last_test_ok", "owner_id"),
        ),
        "skills": _pick(
            assistant_context.get("available_skills"), ("slug", "name", "service", "category", "safety_level")
        ),
        "task_families": task_families,
        "capability_packs": capability_packs,
    }


def _normalize_resource_plan(raw_value: object, assistant_context: dict[str, Any]) -> dict[str, Any]:
    raw = raw_value if isinstance(raw_value, dict) else {}
    plan = {
        "servers": _dict_items(raw.get("servers"), limit=12),
        "agents": _dict_items(raw.get("agents"), limit=8),
        "mcp_servers": _dict_items(raw.get("mcp_servers"), limit=12),
        "skills": _dict_items(raw.get("skills"), limit=12),
        "missing": _string_items(raw.get("missing"), limit=8),
        "notes": _string_items(raw.get("notes"), limit=8),
        "available": _compact_available_resources(assistant_context),
    }
    return plan


def _normalize_node_explanations(raw_value: object) -> dict[str, str]:
    if not isinstance(raw_value, dict):
        return {}
    result: dict[str, str] = {}
    for key, value in raw_value.items():
        node_key = str(key or "").strip()
        explanation = str(value or "").strip()
        if node_key and explanation:
            result[node_key[:100]] = explanation[:500]
    return result


def _normalize_confidence(raw_value: object) -> float | None:
    try:
        value = float(raw_value)
    except (TypeError, ValueError):
        return None
    return max(0.0, min(1.0, value))
