from __future__ import annotations

import re
from collections import defaultdict
from typing import Any

from app.agent_kernel.domain.roles import ROLE_SPECS
from app.agent_kernel.domain.specs import ToolSpec
from app.agent_kernel.memory.compaction import compact_text
from app.agent_kernel.memory.redaction import sanitize_observation_text
from app.agent_kernel.runtime.context import build_ops_prompt_context

_SIMPLE_TEMPLATE_PATTERN = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")


def merge_unique_strings(*groups: list[str]) -> list[str]:
    merged: list[str] = []
    seen: set[str] = set()
    for group in groups:
        for item in group:
            value = str(item or "").strip()
            if not value:
                continue
            lowered = value.lower()
            if lowered in seen:
                continue
            seen.add(lowered)
            merged.append(value)
    return merged


def render_template_value(value: Any, context: dict[str, Any]) -> Any:
    if isinstance(value, str):
        return _SIMPLE_TEMPLATE_PATTERN.sub(lambda match: str(context.get(match.group(1), "")), value)
    if isinstance(value, list):
        return [render_template_value(item, context) for item in value]
    if isinstance(value, dict):
        return {key: render_template_value(item, context) for key, item in value.items()}
    return value


def pipeline_actor_context(run: Any) -> dict[str, Any]:
    fields_cache = getattr(getattr(run, "_state", None), "fields_cache", {}) or {}
    actor = fields_cache.get("triggered_by")
    pipeline = fields_cache.get("pipeline")

    user_id = getattr(run, "triggered_by_id", None)
    username = ""

    if actor is not None:
        user_id = getattr(actor, "id", user_id)
        username = str(getattr(actor, "username", "") or "").strip()

    if user_id is None and pipeline is not None:
        owner = getattr(getattr(pipeline, "_state", None), "fields_cache", {}).get("owner")
        user_id = getattr(pipeline, "owner_id", None)
        if owner is not None:
            user_id = getattr(owner, "id", user_id)
            username = str(getattr(owner, "username", "") or "").strip()

    pipeline_name = ""
    if pipeline is not None:
        pipeline_name = str(getattr(pipeline, "name", "") or "").strip()
    return {
        "user_id": user_id,
        "username_snapshot": username,
        "channel": "pipeline",
        "path": f"/api/studio/pipelines/{run.pipeline_id}/run/",
        "entity_type": "pipeline_run",
        "entity_id": str(run.pk),
        "entity_name": pipeline_name or f"pipeline-run-{run.pk}",
    }


def pipeline_permission_mode(config: dict[str, Any]) -> str:
    mode = str(config.get("permission_mode") or "").strip().upper()
    if mode in {"PLAN", "SAFE", "ASSISTED", "AUTONOMOUS", "AUTO_GUARDED"}:
        return mode
    return "SAFE"


def pipeline_role_slug(config: dict[str, Any]) -> str:
    role = str(config.get("role") or "").strip()
    if role in ROLE_SPECS:
        return role
    if config.get("watcher"):
        return "watcher_daemon"
    return "custom"


def compact_node_outputs_context(node_outputs: dict[str, dict], *, max_nodes: int = 6, max_chars: int = 1200) -> str:
    lines: list[str] = []
    for node_id, output in list(node_outputs.items())[-max_nodes:]:
        sanitized_output = sanitize_observation_text(str(output.get("output") or "").strip()).text
        output_text = compact_text(sanitized_output, limit=max_chars)
        if output_text:
            lines.append(f"=== Output of node [{node_id}] ===\n{output_text}")
    return "\n\n".join(lines)


def _coerce_bool(value: Any, *, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    return default


def build_agent_upstream_context(
    config: dict[str, Any] | None,
    node_outputs: dict[str, dict] | None,
    *,
    default_include: bool = True,
) -> str:
    """Build compact upstream node outputs for agent/react and agent/multi goals.

    Default is to include upstream outputs. Set include_upstream_outputs=false to opt out.
    """
    cfg = config if isinstance(config, dict) else {}
    if not _coerce_bool(cfg.get("include_upstream_outputs"), default=default_include):
        return ""
    if not node_outputs:
        return ""

    try:
        max_nodes = int(cfg.get("max_upstream_nodes", 6) or 6)
    except (TypeError, ValueError):
        max_nodes = 6
    try:
        max_chars = int(cfg.get("max_upstream_chars", 1200) or 1200)
    except (TypeError, ValueError):
        max_chars = 1200
    max_nodes = max(1, min(max_nodes, 12))
    max_chars = max(200, min(max_chars, 4000))
    return compact_node_outputs_context(node_outputs, max_nodes=max_nodes, max_chars=max_chars)


def inject_upstream_into_goal(goal: str, upstream_context: str) -> str:
    goal_text = str(goal or "").strip()
    upstream = str(upstream_context or "").strip()
    if not upstream:
        return goal_text
    if not goal_text:
        return f"## Context from previous pipeline steps\n{upstream}"
    marker = "## Context from previous pipeline steps"
    if marker in goal_text:
        return goal_text
    return f"{goal_text}\n\n{marker}\n{upstream}"


def require_agent_goal(goal: Any) -> str | None:
    """Return an error message if goal is empty after template rendering."""
    if str(goal or "").strip():
        return None
    return "Goal is required for this agent node (empty after template render). Set a non-empty goal."


def build_pipeline_tool_spec(tool_name: str, *, command: str = "") -> ToolSpec:
    lowered_name = (tool_name or "").lower()
    lowered_command = (command or "").lower()
    category = "general"
    risk = "read"
    mutates_state = False
    requires_verification = False

    if lowered_name in {"ssh_execute", "agent/ssh_cmd", "ssh_cmd"} or command:
        category = "ssh"
        risk = "exec"
        requires_verification = True
    elif "keycloak" in lowered_name:
        category = "keycloak"
        risk = "admin"
        mutates_state = True
        requires_verification = True
    elif "docker" in lowered_name or "docker" in lowered_command:
        category = "docker"
        risk = "exec"
        requires_verification = True
    elif "nginx" in lowered_name or "nginx" in lowered_command:
        category = "nginx"
        risk = "exec"
        requires_verification = True
    elif "service" in lowered_name or "systemctl" in lowered_command:
        category = "service"
        risk = "exec"
        requires_verification = True
    elif lowered_name.startswith("mcp"):
        category = "mcp"
        risk = "network"

    return ToolSpec(
        name=tool_name or "pipeline_tool",
        category=category,
        risk=risk,
        description=f"Pipeline node tool: {tool_name}",
        input_schema={},
        mutates_state=mutates_state,
        requires_verification=requires_verification,
        output_compactor="tail",
        runner="pipeline",
    )


def build_pipeline_ops_context(
    *,
    role_slug: str,
    permission_mode: str,
    server_memory_prompt: str,
    operational_recipes_prompt: str,
    tool_spec_lines: str,
    max_iterations: int,
) -> str:
    role_spec = ROLE_SPECS.get(role_slug, ROLE_SPECS["custom"])
    return build_ops_prompt_context(
        role_spec=role_spec,
        permission_mode=permission_mode,
        server_memory_prompt=server_memory_prompt,
        operational_recipes_prompt=operational_recipes_prompt,
        tool_registry_prompt=tool_spec_lines,
        max_iterations=max_iterations,
        session_timeout=0,
    )


def build_enriched_node_context(
    *,
    run: Any,
    context: dict[str, Any],
    node_outputs: dict[str, dict],
) -> defaultdict[str, Any]:
    enriched: defaultdict[str, Any] = defaultdict(str, context)
    enriched["pipeline_name"] = run.pipeline.name
    enriched["run_id"] = str(run.pk)
    enriched["entry_node_id"] = str(run.entry_node_id or "")
    enriched["trigger_type"] = str(getattr(run.trigger, "trigger_type", "") or "")
    enriched["trigger_name"] = str(getattr(run.trigger, "name", "") or "")
    for node_id, state in node_outputs.items():
        output = state.get("output", "") or ""
        error = state.get("error", "") or ""
        enriched[node_id] = output
        enriched[f"{node_id}_output"] = output
        enriched[f"{node_id}_error"] = error
        enriched[f"{node_id}_status"] = state.get("status", "")
    return enriched
