"""
Pipeline Executor

Traverses a Pipeline graph (nodes + edges) in topological order and dispatches
each node to the appropriate execution engine:

  trigger/*              — handled by the caller (just passes context)
  agent/react            — wraps servers.AgentEngine (ReAct loop, CAN execute SSH on server)
  agent/multi            — wraps servers.MultiAgentEngine
  agent/ssh_cmd          — direct SSH command without LLM
  agent/llm_query        — direct LLM call (no SSH, pure reasoning/analysis/decision)
  agent/mcp_call         — direct MCP tools/call on a configured MCP server
  logic/condition        — branches based on previous output
  logic/parallel         — launches multiple agent nodes concurrently
  logic/wait             — pauses execution for N minutes
  logic/human_approval   — waits for human approve/reject via signed URL (email+Telegram)
  output/report          — attaches final markdown to the run
  output/webhook         — POSTs result to an external URL
  output/email           — sends email report via SMTP
  output/telegram        — sends message via Telegram Bot API
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import re
import secrets
from collections import defaultdict, deque
from datetime import timedelta
from threading import Event
from typing import Any

import httpx
from asgiref.sync import sync_to_async as _s2a
from channels.layers import get_channel_layer
from django.utils import timezone

from app.agent_kernel.domain.roles import ROLE_SPECS
from app.agent_kernel.domain.specs import ToolSpec
from app.agent_kernel.hooks.manager import HookManager
from app.agent_kernel.memory.compaction import compact_text
from app.agent_kernel.memory.redaction import sanitize_observation_text
from app.agent_kernel.memory.server_cards import render_server_cards_prompt
from app.agent_kernel.memory.store import DjangoServerMemoryStore
from app.agent_kernel.permissions.engine import PermissionEngine
from app.agent_kernel.runtime.context import build_ops_prompt_context
from app.agent_kernel.sandbox.manager import SandboxManager
from app.core.model_utils import resolve_provider_and_model
from core_ui.activity import log_user_activity_async
from core_ui.audit import audit_context
from servers.mcp_tool_runtime import MCPBoundTool

from .mcp_client import call_mcp_tool
from .models import PipelineRun
from .pipeline_runtime import is_runtime_stop_requested, register_executor, unregister_executor
from .pipeline_validation import validate_pipeline_definition
from .skill_policy import apply_skill_policies, compile_skill_policies
from .skill_registry import normalise_skill_slugs, resolve_skills

logger = logging.getLogger(__name__)
_SIMPLE_TEMPLATE_PATTERN = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")
_PIPELINE_MEMORY_STORE = DjangoServerMemoryStore()


def _s2a_fn(func, thread_sensitive=False):
    return _s2a(func, thread_sensitive=thread_sensitive)


def _merge_unique_strings(*groups: list[str]) -> list[str]:
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


def _render_template_value(value: Any, context: dict[str, Any]) -> Any:
    if isinstance(value, str):
        # Use a narrow placeholder syntax ({name}) so JSON examples and object braces
        # inside prompts/templates do not break interpolation.
        return _SIMPLE_TEMPLATE_PATTERN.sub(lambda match: str(context.get(match.group(1), "")), value)
    if isinstance(value, list):
        return [_render_template_value(item, context) for item in value]
    if isinstance(value, dict):
        return {key: _render_template_value(item, context) for key, item in value.items()}
    return value


def _coerce_mcp_arguments(config: dict[str, Any]) -> tuple[dict[str, Any] | None, str | None]:
    raw_text = str(config.get("arguments_text") or "").strip()
    if raw_text:
        try:
            parsed = json.loads(raw_text)
        except json.JSONDecodeError as exc:
            return None, f"Invalid MCP arguments JSON: {exc}"
        if not isinstance(parsed, dict):
            return None, "MCP arguments must be a JSON object"
        return parsed, None

    raw_arguments = config.get("arguments")
    if isinstance(raw_arguments, dict):
        return raw_arguments, None
    if raw_arguments in (None, ""):
        return {}, None
    return None, "MCP arguments must be a JSON object"


def _pipeline_actor_context(run: PipelineRun) -> dict[str, Any]:
    actor = getattr(run, "triggered_by", None) or getattr(getattr(run, "pipeline", None), "owner", None)
    username = ""
    user_id = None
    if actor is not None:
        user_id = getattr(actor, "id", None)
        username = str(getattr(actor, "username", "") or "").strip()
    return {
        "user_id": user_id,
        "username_snapshot": username,
        "channel": "pipeline",
        "path": f"/api/studio/pipelines/{run.pipeline_id}/run/",
        "entity_type": "pipeline_run",
        "entity_id": str(run.pk),
        "entity_name": str(getattr(getattr(run, "pipeline", None), "name", "") or f"pipeline-run-{run.pk}"),
    }


def _save_server_command_history(*, server_id: int, user_id: int | None, command: str, output: str, exit_code: int | None) -> None:
    from servers.models import ServerCommandHistory

    ServerCommandHistory.objects.create(
        server_id=server_id,
        user_id=user_id,
        command=command,
        output=(output or "")[:10000],
        exit_code=exit_code,
    )


async def _log_pipeline_ssh_command(
    *,
    run: PipelineRun,
    server,
    node_id: str,
    command: str,
    exit_code: int | None,
    output: str = "",
    error: str = "",
) -> None:
    actor_ctx = _pipeline_actor_context(run)
    status = "success" if exit_code == 0 and not error else "error"
    combined_output = error or output
    await log_user_activity_async(
        user_id=actor_ctx.get("user_id"),
        username_snapshot=str(actor_ctx.get("username_snapshot") or ""),
        category="terminal",
        action="server_execute_command",
        status=status,
        description=command[:4000],
        entity_type="server",
        entity_id=str(server.id),
        entity_name=server.name,
        metadata={
            "source": "pipeline_ssh_cmd",
            "pipeline_id": run.pipeline_id,
            "pipeline_run_id": run.pk,
            "node_id": node_id,
            "exit_code": exit_code,
            "output_excerpt": combined_output[:4000],
        },
    )
    await _s2a_fn(_save_server_command_history, thread_sensitive=True)(
        server_id=server.id,
        user_id=actor_ctx.get("user_id"),
        command=command,
        output=combined_output,
        exit_code=exit_code,
    )


def _mcp_result_to_text(result: dict[str, Any]) -> str:
    parts: list[str] = []

    for item in result.get("content") or []:
        if not isinstance(item, dict):
            continue
        if item.get("type") == "text" and item.get("text"):
            parts.append(str(item["text"]))
        elif item.get("type") == "json" and "json" in item:
            parts.append(json.dumps(item["json"], ensure_ascii=False, indent=2))
        elif item.get("type") == "image":
            parts.append("[MCP returned image content]")

    structured = result.get("structuredContent")
    if structured is not None and not parts:
        parts.append(json.dumps(structured, ensure_ascii=False, indent=2))

    if not parts:
        parts.append(json.dumps(result, ensure_ascii=False, indent=2))

    return "\n\n".join(part for part in parts if part)


async def _load_owned_servers(owner, server_ids: list[int]):
    from servers.models import Server

    if not server_ids:
        return []
    return await _s2a_fn(lambda: list(Server.objects.filter(id__in=server_ids, user=owner)))()


async def _load_owned_agent_config(owner, agent_config_id: int):
    from studio.models import AgentConfig

    return await _s2a_fn(
        lambda: AgentConfig.objects.filter(id=agent_config_id, owner=owner).prefetch_related("mcp_servers", "server_scope").first()
    )()


async def _load_agent_scope_ids(agent_conf) -> set[int]:
    if not agent_conf:
        return set()
    owner = getattr(agent_conf, "owner", None)
    return set(await _s2a_fn(lambda: list(agent_conf.server_scope.filter(user=owner).values_list("id", flat=True)))())


def _pipeline_permission_mode(config: dict[str, Any]) -> str:
    mode = str(config.get("permission_mode") or "").strip().upper()
    if mode in {"PLAN", "SAFE", "ASSISTED", "AUTONOMOUS", "AUTO_GUARDED"}:
        return mode
    return "SAFE"


def _pipeline_role_slug(config: dict[str, Any]) -> str:
    role = str(config.get("role") or "").strip()
    if role in ROLE_SPECS:
        return role
    if config.get("watcher"):
        return "watcher_daemon"
    return "custom"


async def _load_pipeline_server_memory(owner, config: dict[str, Any], context: dict[str, Any]) -> str:
    raw_server_ids = config.get("server_ids") or []
    if config.get("server_id") and not raw_server_ids:
        raw_server_ids = [config.get("server_id")]

    server_ids: list[int] = []
    for value in raw_server_ids[:3]:
        try:
            server_ids.append(int(value))
        except (TypeError, ValueError):
            continue
    if not server_ids and context.get("target_server_id"):
        with contextlib.suppress(TypeError, ValueError):
            server_ids.append(int(context.get("target_server_id")))

    if not server_ids:
        return "Память по серверам для этого pipeline node не выбрана."

    cards = []
    servers = await _load_owned_servers(owner, server_ids)
    for server in servers[:3]:
        try:
            cards.append(await _PIPELINE_MEMORY_STORE.get_server_card(server.id))
        except Exception as exc:
            logger.debug("Failed to load pipeline server memory for %s: %s", server.id, exc)
    return render_server_cards_prompt(cards, max_cards=3, max_records=5)


async def _load_pipeline_operational_recipes(
    owner,
    config: dict[str, Any],
    context: dict[str, Any],
    *,
    role_slug: str,
    query: str,
) -> str:
    raw_server_ids = config.get("server_ids") or []
    if config.get("server_id") and not raw_server_ids:
        raw_server_ids = [config.get("server_id")]

    server_ids: list[int] = []
    for value in raw_server_ids[:3]:
        try:
            server_ids.append(int(value))
        except (TypeError, ValueError):
            continue
    if not server_ids and context.get("target_server_id"):
        with contextlib.suppress(TypeError, ValueError):
            server_ids.append(int(context.get("target_server_id")))

    group_ids: list[int] = []
    if server_ids:
        for server in await _load_owned_servers(owner, server_ids):
            if getattr(server, "group_id", None):
                group_ids.append(server.group_id)

    recipe_query = "\n".join(part for part in [query, role_slug] if part).strip()
    return await _PIPELINE_MEMORY_STORE.build_operational_recipes_prompt(
        recipe_query,
        server_ids=server_ids,
        group_ids=list(dict.fromkeys(group_ids)),
        limit=4,
    )


def _compact_node_outputs_context(node_outputs: dict[str, dict], *, max_nodes: int = 6, max_chars: int = 1200) -> str:
    lines: list[str] = []
    for nid, out in list(node_outputs.items())[-max_nodes:]:
        sanitized_output = sanitize_observation_text(str(out.get("output") or "").strip()).text
        output_text = compact_text(sanitized_output, limit=max_chars)
        if output_text:
            lines.append(f"=== Output of node [{nid}] ===\n{output_text}")
    return "\n\n".join(lines)


def _build_pipeline_tool_spec(tool_name: str, *, command: str = "") -> ToolSpec:
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


def _build_pipeline_ops_context(
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


# ---------------------------------------------------------------------------
# Topological sort (Kahn's algorithm)
# ---------------------------------------------------------------------------


def _topo_sort(nodes: list[dict], edges: list[dict]) -> list[list[dict]]:
    """
    Returns nodes in execution layers (BFS topological order).
    Nodes in the same layer can run in parallel.
    """
    id_to_node = {n["id"]: n for n in nodes}
    in_degree: dict[str, int] = defaultdict(int)
    children: dict[str, list[str]] = defaultdict(list)

    for edge in edges:
        src = edge["source"]
        dst = edge["target"]
        children[src].append(dst)
        in_degree[dst] += 1

    # Nodes with no incoming edges (triggers / entry points)
    queue: deque[str] = deque(nid for nid in id_to_node if in_degree[nid] == 0)
    layers: list[list[dict]] = []

    while queue:
        layer_size = len(queue)
        layer: list[dict] = []
        for _ in range(layer_size):
            nid = queue.popleft()
            layer.append(id_to_node[nid])
            for child in children[nid]:
                in_degree[child] -= 1
                if in_degree[child] == 0:
                    queue.append(child)
        if layer:
            layers.append(layer)

    return layers


# ---------------------------------------------------------------------------
# Node executor helpers
# ---------------------------------------------------------------------------


async def _execute_agent_react(node: dict, context: dict, run: PipelineRun) -> dict:
    """Execute an agent/react node using AgentEngine."""
    from servers.agent_engine import AgentEngine
    from servers.models import AgentRun, ServerAgent

    config = node.get("data", {})
    node_id = node.get("id")
    agent_config_id = config.get("agent_config_id")
    server_ids = config.get("server_ids", [])
    mcp_server_ids = config.get("mcp_server_ids", [])
    node_skill_slugs = normalise_skill_slugs(config.get("skill_slugs"))
    goal = config.get("goal", "")
    owner = await _s2a_fn(lambda: run.pipeline.owner)()

    # Substitute known context values and leave missing ones blank.
    goal = _render_template_value(goal, context)

    servers = await _load_owned_servers(owner, server_ids) if server_ids else []

    # Create a temporary ServerAgent from AgentConfig or inline config
    if agent_config_id:
        try:
            agent_conf_pk = int(agent_config_id)
        except (TypeError, ValueError):
            return {"status": "failed", "error": f"Invalid agent config id: {agent_config_id}"}
        agent_conf = await _load_owned_agent_config(owner, agent_conf_pk)
        if agent_conf is None:
            return {"status": "failed", "error": f"Agent config not found: {agent_config_id}"}
        system_prompt = _render_template_value(agent_conf.system_prompt, context)
        instructions = _render_template_value(agent_conf.instructions, context)
        max_iterations = agent_conf.max_iterations
        model = agent_conf.model
        tools_config = dict.fromkeys(agent_conf.allowed_tools or [], True)
        mcp_servers = await _s2a_fn(lambda: list(agent_conf.mcp_servers.filter(owner=owner)))()
        skill_slugs = _merge_unique_strings(list(agent_conf.skill_slugs or []), node_skill_slugs)
        allowed_server_ids = await _load_agent_scope_ids(agent_conf)
        if allowed_server_ids:
            disallowed = [server_id for server_id in server_ids if server_id not in allowed_server_ids]
            if disallowed:
                return {
                    "status": "failed",
                    "error": f"Node references servers outside agent scope: {disallowed}",
                }
    else:
        system_prompt = _render_template_value(config.get("system_prompt", ""), context)
        instructions = _render_template_value(config.get("instructions", ""), context)
        max_iterations = config.get("max_iterations", 10)
        model = config.get("model", "gemini-2.0-flash-exp")
        tools_config = dict.fromkeys(config.get("allowed_tools", []) or [], True)
        from .models import MCPServerPool

        mcp_servers = (
            await _s2a_fn(lambda: list(MCPServerPool.objects.filter(id__in=mcp_server_ids, owner=owner)))()
            if mcp_server_ids
            else []
        )
        skill_slugs = node_skill_slugs

    skills, skill_errors = resolve_skills(skill_slugs)

    if server_ids and not servers:
        return {"status": "failed", "error": f"Servers not found: {server_ids}"}
    if not servers and not mcp_servers and not skills:
        return {"status": "failed", "error": "Configure at least one server, one MCP server, or one skill for this agent node"}

    model_preference, specific_model = resolve_provider_and_model(
        config.get("provider"),
        model,
        default_provider="auto",
    )

    sa = ServerAgent(
        name=f"pipeline_node_{node['id']}",
        mode=ServerAgent.MODE_FULL,
        goal=goal,
        system_prompt=system_prompt,
        ai_prompt=instructions,
        max_iterations=max_iterations,
        tools_config=tools_config,
        allow_multi_server=len(servers) > 1,
    )

    engine = AgentEngine(
        agent=sa,
        servers=servers,
        user=owner,
        event_callback=_make_run_event_callback(run, node["id"]),
        model_preference=model_preference,
        specific_model=specific_model,
        mcp_servers=mcp_servers,
        skills=skills,
        skill_errors=skill_errors,
    )

    logger.info(
        "pipeline run %s node %s agent/react start: provider=%s model=%s servers=%s mcp_servers=%s skills=%s",
        run.pk,
        node_id,
        model_preference,
        specific_model,
        [srv.name for srv in servers],
        [srv.name for srv in mcp_servers],
        [skill.slug for skill in skills],
    )
    agent_run: AgentRun = await engine.run()
    logger.info(
        "pipeline run %s node %s agent/react done: agent_run_id=%s status=%s report_chars=%s",
        run.pk,
        node_id,
        agent_run.pk,
        agent_run.status,
        len(agent_run.final_report or ""),
    )
    return {
        "status": "completed" if agent_run.status == "completed" else "failed",
        "agent_run_id": agent_run.pk,
        "output": agent_run.final_report or "",
        "error": agent_run.ai_analysis if agent_run.status != "completed" else "",
    }


async def _execute_agent_multi(node: dict, context: dict, run: PipelineRun) -> dict:
    """Execute an agent/multi node using MultiAgentEngine."""
    from servers.models import ServerAgent
    from servers.multi_agent_engine import MultiAgentEngine

    config = node.get("data", {})
    server_ids = config.get("server_ids", [])
    mcp_server_ids = config.get("mcp_server_ids", [])
    node_skill_slugs = normalise_skill_slugs(config.get("skill_slugs"))
    goal = config.get("goal", "")
    owner = await _s2a_fn(lambda: run.pipeline.owner)()

    goal = _render_template_value(goal, context)

    servers = await _load_owned_servers(owner, server_ids) if server_ids else []

    agent_config_id = config.get("agent_config_id")
    if agent_config_id:
        try:
            agent_conf_pk = int(agent_config_id)
        except (TypeError, ValueError):
            return {"status": "failed", "error": f"Invalid agent config id: {agent_config_id}"}
        agent_conf = await _load_owned_agent_config(owner, agent_conf_pk)
        if agent_conf is None:
            return {"status": "failed", "error": f"Agent config not found: {agent_config_id}"}
        system_prompt = _render_template_value(agent_conf.system_prompt, context)
        max_iterations = agent_conf.max_iterations
        model = agent_conf.model
        tools_config = dict.fromkeys(agent_conf.allowed_tools or [], True)
        mcp_servers = await _s2a_fn(lambda: list(agent_conf.mcp_servers.filter(owner=owner)))()
        skill_slugs = _merge_unique_strings(list(agent_conf.skill_slugs or []), node_skill_slugs)
        allowed_server_ids = await _load_agent_scope_ids(agent_conf)
        if allowed_server_ids:
            disallowed = [server_id for server_id in server_ids if server_id not in allowed_server_ids]
            if disallowed:
                return {
                    "status": "failed",
                    "error": f"Node references servers outside agent scope: {disallowed}",
                }
    else:
        system_prompt = _render_template_value(config.get("system_prompt", ""), context)
        max_iterations = config.get("max_iterations", 20)
        model = config.get("model", "gemini-2.0-flash-exp")
        tools_config = dict.fromkeys(config.get("allowed_tools", []) or [], True)
        from .models import MCPServerPool

        mcp_servers = (
            await _s2a_fn(lambda: list(MCPServerPool.objects.filter(id__in=mcp_server_ids, owner=owner)))()
            if mcp_server_ids
            else []
        )
        skill_slugs = node_skill_slugs

    skills, skill_errors = resolve_skills(skill_slugs)

    if server_ids and not servers:
        return {"status": "failed", "error": f"Servers not found: {server_ids}"}
    if not servers and not mcp_servers and not skills:
        return {
            "status": "failed",
            "error": "Configure at least one server, one MCP server, or one skill for this multi agent node",
        }

    model_preference, specific_model = resolve_provider_and_model(
        config.get("provider"),
        model,
        default_provider="auto",
    )

    sa = ServerAgent(
        name=f"pipeline_multi_{node['id']}",
        mode=ServerAgent.MODE_MULTI,
        goal=goal,
        system_prompt=system_prompt,
        max_iterations=max_iterations,
        tools_config=tools_config,
        allow_multi_server=True,
    )

    engine = MultiAgentEngine(
        agent=sa,
        servers=servers,
        user=owner,
        event_callback=_make_run_event_callback(run, node["id"]),
        model_preference=model_preference,
        specific_model=specific_model,
        mcp_servers=mcp_servers,
        skills=skills,
        skill_errors=skill_errors,
    )

    agent_run = await engine.run()
    return {
        "status": "completed" if agent_run.status == "completed" else "failed",
        "agent_run_id": agent_run.pk,
        "output": agent_run.final_report or "",
        "error": agent_run.ai_analysis if agent_run.status != "completed" else "",
    }


async def _execute_agent_ssh_cmd(node: dict, context: dict, run: PipelineRun) -> dict:
    """Execute a direct SSH command without LLM."""
    import asyncssh

    from servers.models import Server

    config = node.get("data", {})
    server_id = config.get("server_id")
    command = config.get("command", "")
    preflight_commands = list(config.get("preflight_commands") or [])
    verification_commands = list(config.get("verification_commands") or [])

    with contextlib.suppress(KeyError, ValueError):
        command = command.format(**context)

    if not server_id:
        return {
            "status": "skipped",
            "output": "⚠️ No server configured for this SSH node. Click the node → select a Server in the config panel.",
        }
    if not command:
        # If an AgentConfig is attached, the node was likely meant to be agent/react — delegate.
        # Normalise server_id → server_ids so _execute_agent_react finds the server.
        if config.get("agent_config_id") or config.get("goal"):
            patched_node = dict(node)
            patched_data = dict(config)
            if server_id and not patched_data.get("server_ids"):
                patched_data["server_ids"] = [server_id]
            patched_node["data"] = patched_data
            return await _execute_agent_react(patched_node, context, run)
        return {
            "status": "failed",
            "error": "Команда не задана. Откройте узел в редакторе и введите команду в поле «Command», "
                     "или смените тип узла на «ReAct Agent» если нужен ИИ-агент.",
        }

    owner = await _s2a_fn(lambda: run.pipeline.owner)()
    try:
        server = await _s2a_fn(Server.objects.get)(id=server_id, user=owner)
    except Server.DoesNotExist:
        return {"status": "failed", "error": f"Server not found: {server_id}"}

    permission_engine = PermissionEngine(mode=_pipeline_permission_mode(config))
    sandbox_manager = SandboxManager()
    hook_manager = HookManager()
    spec = _build_pipeline_tool_spec("ssh_execute", command=command)
    decision = permission_engine.evaluate(spec, {"command": command})
    if not decision.allowed and not preflight_commands:
        return {
            "status": "failed",
            "error": decision.reason,
            "output": "",
        }

    try:
        from servers.monitor import _build_connect_kwargs

        connect_kwargs = await _build_connect_kwargs(server)
        connect_kwargs["connect_timeout"] = 30

        async with asyncssh.connect(**connect_kwargs) as conn:
            combined_outputs: list[str] = []

            async def _run_remote_command(command_text: str, *, stage: str) -> tuple[int, str]:
                stage_profile = decision.sandbox_profile if stage == "command" else "ops_read"
                sandbox_decision = sandbox_manager.validate(spec, {"command": command_text}, stage_profile)
                if not sandbox_decision.allowed:
                    raise RuntimeError(sandbox_decision.reason)
                remote_result = await conn.run(command_text, timeout=120)
                remote_output = remote_result.stdout + (("\n" + remote_result.stderr) if remote_result.stderr else "")
                compacted_output = await hook_manager.post_tool_use("ssh_execute", remote_output)
                permission_engine.record_success(spec, {"command": command_text}, compacted_output)
                await _log_pipeline_ssh_command(
                    run=run,
                    server=server,
                    node_id=str(node.get("id") or ""),
                    command=f"[{stage}] {command_text}",
                    exit_code=remote_result.exit_status,
                    output=compacted_output,
                )
                combined_outputs.append(f"## {stage}\n{compacted_output}")
                return remote_result.exit_status, compacted_output

            for preflight_command in preflight_commands:
                rendered = _render_template_value(preflight_command, context)
                exit_code, _ = await _run_remote_command(str(rendered), stage="preflight")
                if exit_code != 0:
                    return {
                        "status": "failed",
                        "error": f"Preflight command failed: {rendered}",
                        "output": "\n\n".join(combined_outputs),
                    }

            decision = permission_engine.evaluate(spec, {"command": command})
            if not decision.allowed:
                return {"status": "failed", "error": decision.reason, "output": "\n\n".join(combined_outputs)}

            exit_code, output = await _run_remote_command(command, stage="command")
            verification_summary = permission_engine.verification_summary()
            if verification_commands:
                for verify_command in verification_commands:
                    rendered = _render_template_value(verify_command, context)
                    verify_exit_code, _ = await _run_remote_command(str(rendered), stage="verification")
                    if verify_exit_code != 0:
                        return {
                            "status": "failed",
                            "error": f"Verification command failed: {rendered}",
                            "output": "\n\n".join(combined_outputs),
                        }
                verification_summary = permission_engine.verification_summary()
                combined_outputs.append(f"## verification_summary\n{verification_summary}")

            full_output = "\n\n".join(combined_outputs) if combined_outputs else output
            return {
                "status": "completed" if exit_code == 0 else "failed",
                "output": full_output,
                "exit_code": exit_code,
                "verification_summary": verification_summary,
                "error": "" if exit_code == 0 else output,
            }
    except Exception as exc:
        error_text = f"{exc} (server: {server.name} [{server.username}@{server.host}])"
        await _log_pipeline_ssh_command(
            run=run,
            server=server,
            node_id=str(node.get("id") or ""),
            command=command,
            exit_code=-1,
            error=error_text,
        )
        return {
            "status": "failed",
            "error": error_text,
        }


def _resolve_llm_provider_and_model(config: dict) -> tuple[str, str]:
    provider, model = resolve_provider_and_model(
        config.get("provider"),
        config.get("model"),
        default_provider="gemini",
    )
    return provider, model or "gemini-2.0-flash-exp"


async def _execute_agent_llm_query(node: dict, context: dict, node_outputs: dict[str, dict], run: PipelineRun) -> dict:
    """
    Direct LLM query — no SSH needed.
    Sends a prompt (with all previous node outputs as context) to the chosen provider (Gemini, OpenAI, Grok, Claude)
    and returns the response.
    """
    import time

    config = node.get("data", {})
    prompt_template = config.get("prompt", "")
    system_prompt = config.get("system_prompt", "You are a helpful DevOps assistant.")
    include_all_outputs = config.get("include_all_outputs", True)
    purpose = str(config.get("purpose") or "opssummary").strip() or "opssummary"
    permission_mode = _pipeline_permission_mode(config)
    role_slug = _pipeline_role_slug(config)
    max_context_nodes = max(1, min(int(config.get("max_context_nodes", 6) or 6), 12))
    max_output_context_chars = max(200, min(int(config.get("max_output_chars", 1200) or 1200), 4000))
    provider, specific_model = _resolve_llm_provider_and_model(config)

    if not prompt_template:
        return {"status": "failed", "error": "No prompt configured for llm_query node"}

    # Build rich context string from all previous node outputs
    outputs_context = (
        _compact_node_outputs_context(node_outputs, max_nodes=max_context_nodes, max_chars=max_output_context_chars)
        if include_all_outputs
        else ""
    )

    substitutions = dict(context)
    substitutions["all_outputs"] = outputs_context
    prompt = _render_template_value(prompt_template, substitutions)

    owner = await _s2a_fn(lambda: run.pipeline.owner)()
    server_memory_prompt = await _load_pipeline_server_memory(owner, config, context)
    operational_recipes_prompt = await _load_pipeline_operational_recipes(
        owner,
        config,
        context,
        role_slug=role_slug,
        query=prompt,
    )
    ops_context = _build_pipeline_ops_context(
        role_slug=role_slug,
        permission_mode=permission_mode,
        server_memory_prompt=server_memory_prompt,
        operational_recipes_prompt=operational_recipes_prompt,
        tool_spec_lines="- llm_query: reasoning / summarization / planning [general / read]",
        max_iterations=1,
    )

    full_prompt = f"{system_prompt}\n\n{prompt}" if system_prompt else prompt
    if outputs_context and "{all_outputs}" not in prompt_template and include_all_outputs:
        full_prompt = f"{system_prompt}\n\n{ops_context}\n\n## Context from previous pipeline steps:\n{outputs_context}\n\n## Your task:\n{prompt}"
    else:
        full_prompt = f"{system_prompt}\n\n{ops_context}\n\n{prompt}" if system_prompt else f"{ops_context}\n\n{prompt}"

    try:
        from app.core.llm import LLMProvider

        t0 = time.time()
        llm = LLMProvider()
        output_chunks: list[str] = []
        async for chunk in llm.stream_chat(
            full_prompt,
            model=provider,
            specific_model=specific_model or None,
            purpose=purpose,
        ):
            output_chunks.append(chunk)
        output_text = compact_text("".join(output_chunks), limit=6000)
        elapsed = int((time.time() - t0) * 1000)
        logger.info("llm_query node %s: %s/%s %.1fs, %d chars", node.get("id"), provider, specific_model, elapsed / 1000, len(output_text))

        if output_text.strip().startswith("Error:"):
            return {"status": "failed", "error": output_text.strip(), "output": output_text}
        return {"status": "completed", "output": output_text}
    except Exception as exc:
        logger.exception("llm_query node %s failed", node.get("id"))
        return {"status": "failed", "error": str(exc)}


async def _execute_agent_mcp_call(
    node: dict,
    context: dict,
    run: PipelineRun,
    executed_mcp_tools: set[str] | None = None,
) -> dict:
    """Execute a direct MCP tools/call request against a configured MCP server."""
    from .models import MCPServerPool

    config = node.get("data", {})
    owner = await _s2a_fn(lambda: run.pipeline.owner)()
    mcp_server_id = config.get("mcp_server_id")
    tool_name = str(config.get("tool_name") or "").strip()
    node_skill_slugs = normalise_skill_slugs(config.get("skill_slugs"))

    if not mcp_server_id:
        return {"status": "failed", "error": "Select an MCP server for this node"}
    if not tool_name:
        return {"status": "failed", "error": "Select an MCP tool for this node"}

    arguments_template, error = _coerce_mcp_arguments(config)
    if error:
        return {"status": "failed", "error": error}

    try:
        mcp_server = await _s2a_fn(MCPServerPool.objects.get)(id=int(mcp_server_id), owner=owner)
    except MCPServerPool.DoesNotExist:
        return {"status": "failed", "error": f"MCP server not found: {mcp_server_id}"}
    except (TypeError, ValueError):
        return {"status": "failed", "error": f"Invalid MCP server id: {mcp_server_id}"}

    arguments = _render_template_value(arguments_template or {}, context)
    skills, skill_errors = resolve_skills(node_skill_slugs)
    skill_policies, policy_errors = compile_skill_policies(skills)
    if skill_errors or policy_errors:
        return {
            "status": "failed",
            "error": f"Skill policy validation failed: {'; '.join([*skill_errors, *policy_errors])}",
        }

    binding = MCPBoundTool(
        action_name=f"pipeline_{node.get('id') or 'node'}_{tool_name}",
        server=mcp_server,
        tool_name=tool_name,
        description=f"Pipeline MCP call for {tool_name}",
        input_schema=None,
    )
    permission_engine = PermissionEngine(mode=_pipeline_permission_mode(config))
    sandbox_manager = SandboxManager()
    hook_manager = HookManager()
    spec = _build_pipeline_tool_spec(f"mcp_{tool_name}")
    decision = permission_engine.evaluate(spec, arguments)
    if not decision.allowed:
        return {"status": "failed", "error": decision.reason}
    prepared_args, policy_messages, policy_error = apply_skill_policies(
        skill_policies,
        binding,
        arguments,
        executed_mcp_tools if executed_mcp_tools is not None else set(),
    )
    if policy_error:
        return {
            "status": "failed",
            "error": policy_error,
        }
    sandbox_decision = sandbox_manager.validate(spec, prepared_args, decision.sandbox_profile)
    if not sandbox_decision.allowed:
        return {"status": "failed", "error": sandbox_decision.reason}

    try:
        logger.info(
            "pipeline run %s node %s mcp_call start: server=%s tool=%s args=%s",
            run.pk,
            node.get("id"),
            mcp_server.name,
            tool_name,
            json.dumps(prepared_args, ensure_ascii=False)[:800],
        )
        result = await call_mcp_tool(mcp_server, tool_name, prepared_args)
        output = _mcp_result_to_text(result)
        if decision.notes:
            output = "\n".join([*decision.notes, output]) if output else "\n".join(decision.notes)
        if policy_messages:
            output = "\n".join([*policy_messages, output]) if output else "\n".join(policy_messages)
        output = await hook_manager.post_tool_use(tool_name, output)
        logger.info(
            "pipeline run %s node %s mcp_call done: server=%s tool=%s is_error=%s output_chars=%s",
            run.pk,
            node.get("id"),
            mcp_server.name,
            tool_name,
            bool(result.get("isError")),
            len(output),
        )
        actor_ctx = _pipeline_actor_context(run)
        await log_user_activity_async(
            user_id=actor_ctx.get("user_id"),
            username_snapshot=str(actor_ctx.get("username_snapshot") or ""),
            category="mcp",
            action="mcp_call",
            status="error" if result.get("isError") else "success",
            description=f"{mcp_server.name}.{tool_name}",
            entity_type="pipeline_run",
            entity_id=str(run.pk),
            entity_name=actor_ctx.get("entity_name") or "",
            metadata={
                "node_id": str(node.get("id") or ""),
                "mcp_server_id": mcp_server.id,
                "mcp_server_name": mcp_server.name,
                "tool_name": tool_name,
                "arguments": prepared_args,
                "is_error": bool(result.get("isError")),
                "output_excerpt": output[:4000],
            },
        )
        if not result.get("isError"):
            permission_engine.record_success(spec, prepared_args, output)
        if result.get("isError"):
            return {
                "status": "failed",
                "error": output or f"MCP tool '{tool_name}' returned an error",
                "output": output,
                "raw_result": result,
            }
        if executed_mcp_tools is not None:
            executed_mcp_tools.add(tool_name)
        return {
            "status": "completed",
            "output": output,
            "raw_result": result,
        }
    except Exception as exc:
        logger.exception("mcp_call node %s failed", node.get("id"))
        actor_ctx = _pipeline_actor_context(run)
        await log_user_activity_async(
            user_id=actor_ctx.get("user_id"),
            username_snapshot=str(actor_ctx.get("username_snapshot") or ""),
            category="mcp",
            action="mcp_call",
            status="error",
            description=f"{mcp_server.name}.{tool_name}" if "mcp_server" in locals() else tool_name,
            entity_type="pipeline_run",
            entity_id=str(run.pk),
            entity_name=actor_ctx.get("entity_name") or "",
            metadata={
                "node_id": str(node.get("id") or ""),
                "error": str(exc),
            },
        )
        return {"status": "failed", "error": str(exc)}


async def _execute_output_email(node: dict, context: dict, node_outputs: dict[str, dict], run: PipelineRun) -> dict:
    """
    Send an email report via SMTP.
    Uses Django EMAIL_* settings or per-node SMTP config.
    """
    import smtplib
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText

    from django.conf import settings

    config = node.get("data", {})
    g_to, g_host, g_user, g_pass, g_from = _global_email_defaults()

    to_email = (config.get("to_email") or g_to or "").strip()
    to_email = _normalize_email_recipient(to_email, (config.get("smtp_host") or "").strip() or g_host)
    if not to_email:
        return {
            "status": "failed",
            "error": "No recipient email. Set PIPELINE_NOTIFY_EMAIL in .env or fill in the node.",
        }

    subject_template = config.get("subject", f"Pipeline Report: {run.pipeline.name}")
    body_template = config.get("body", "")

    # context is already enriched with {nid}, {nid_output}, {nid_error} from _execute_node
    subs = dict(context)

    # Format subject
    try:
        subject = subject_template.format_map(subs)
    except (KeyError, ValueError):
        subject = subject_template

    # Build body
    if body_template:
        try:
            body = body_template.format_map(subs)
        except (KeyError, ValueError):
            body = body_template
    else:
        lines = [
            f"# Pipeline Run Report: {run.pipeline.name}",
            f"Status: {run.status}",
            "",
        ]
        for nid, state in node_outputs.items():
            if state.get("output"):
                lines.append(f"## [{nid}]")
                lines.append(state["output"][:2000])
                lines.append("")
        body = "\n".join(lines)

    # SMTP config: node overrides global Django settings which override hardcoded defaults
    smtp_host = (config.get("smtp_host") or "").strip() or g_host or getattr(settings, "EMAIL_HOST", "smtp.gmail.com")
    smtp_port = int((config.get("smtp_port") or getattr(settings, "EMAIL_PORT", 587)) or 587)
    smtp_user = (config.get("smtp_user") or "").strip() or g_user or getattr(settings, "EMAIL_HOST_USER", "")
    smtp_password = (config.get("smtp_password") or "").strip() or g_pass or getattr(settings, "EMAIL_HOST_PASSWORD", "")
    from_email = (config.get("from_email") or "").strip() or g_from or smtp_user or "pipeline@noreply.local"
    # SMTP servers (Yandex, etc.) reject sender if From is not a real mailbox on their side
    from_email = _resolve_from_email(from_email, smtp_user, smtp_host)
    use_tls = smtp_port in (587, 465)

    def _send_sync():
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = from_email
        msg["To"] = to_email
        msg.attach(MIMEText(body, "plain", "utf-8"))
        # Try Markdown as HTML alternative
        try:
            import markdown
            html_body = markdown.markdown(body)
            msg.attach(MIMEText(f"<html><body>{html_body}</body></html>", "html", "utf-8"))
        except ImportError:
            pass

        # Port 465 = SSL from the start (Yandex, etc.); 587 = STARTTLS
        if smtp_port == 465:
            with smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=30) as server:
                if smtp_user and smtp_password:
                    server.login(smtp_user, smtp_password)
                server.sendmail(from_email, to_email.split(","), msg.as_string())
        else:
            with smtplib.SMTP(smtp_host, smtp_port, timeout=30) as server:
                server.ehlo()
                if use_tls and smtp_port == 587:
                    server.starttls()
                    server.ehlo()
                if smtp_user and smtp_password:
                    server.login(smtp_user, smtp_password)
                server.sendmail(from_email, to_email.split(","), msg.as_string())

    try:
        await asyncio.get_event_loop().run_in_executor(None, _send_sync)
        return {"status": "completed", "output": f"✉️ Email sent to {to_email} | Subject: {subject}"}
    except Exception as exc:
        logger.warning("output/email node %s failed: %s", node.get("id"), exc)
        return {"status": "failed", "error": f"SMTP error: {exc}"}


async def _execute_logic_condition(
    node: dict, context: dict, node_outputs: dict[str, dict], run: PipelineRun
) -> dict:
    """Evaluate condition against previous node output."""
    config = node.get("data", {})
    source_node_id = config.get("source_node_id", "")

    source_output = node_outputs.get(source_node_id, {}).get("output", "")

    # Simple keyword condition
    check_type = config.get("check_type", "contains")
    check_value = config.get("check_value", "")

    passed = False
    if check_type == "contains":
        passed = check_value.lower() in source_output.lower()
    elif check_type == "not_contains":
        passed = check_value.lower() not in source_output.lower()
    elif check_type == "status_ok":
        passed = node_outputs.get(source_node_id, {}).get("status") == "completed"
    elif check_type == "status_failed":
        passed = node_outputs.get(source_node_id, {}).get("status") == "failed"
    elif check_type == "always_true":
        passed = True

    return {"status": "completed", "passed": passed, "output": str(passed)}


async def _execute_output_report(node: dict, context: dict, node_outputs: dict[str, dict], run: PipelineRun) -> dict:
    """Compile a markdown report from all node outputs."""
    config = node.get("data", {})
    template = config.get("template", "")

    if template:
        # Render what we can and leave missing values blank instead of leaking raw placeholders.
        report = _render_template_value(template, context)
    else:
        lines = [f"# Pipeline Run Report: {run.pipeline.name}\n"]
        for nid, state in node_outputs.items():
            lines.append(f"## Node `{nid}`")
            lines.append(f"**Status:** {state.get('status', 'unknown')}")
            if state.get("output"):
                lines.append(f"```\n{state['output'][:2000]}\n```")
            if state.get("error"):
                lines.append(f"**Error:** {state['error']}")
            lines.append("")
        report = "\n".join(lines)

    await _s2a_fn(PipelineRun.objects.filter(pk=run.pk).update)(summary=report)
    return {"status": "completed", "output": report}


async def _execute_output_webhook(node: dict, context: dict, node_outputs: dict[str, dict]) -> dict:
    """POST the pipeline results to an external webhook URL."""
    config = node.get("data", {})
    url = config.get("url", "")
    if not url:
        return {"status": "failed", "error": "No URL configured"}

    payload = {
        "context": context,
        "outputs": {k: {"status": v.get("status"), "output": v.get("output", "")[:1000]} for k, v in node_outputs.items()},
    }
    extra_payload = config.get("extra_payload", {})
    payload.update(extra_payload)

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(url, json=payload)
            return {
                "status": "completed",
                "output": f"POST {url} → {resp.status_code}",
                "http_status": resp.status_code,
            }
    except Exception as exc:
        return {"status": "failed", "error": str(exc)}


def _load_notif_cfg() -> dict:
    """Load .notification_config.json (saved via UI) merged with env/Django settings."""
    try:
        from studio.views import _load_notif_config

        return _load_notif_config()
    except Exception:
        pass
    # Minimal fallback when views can't be imported
    try:
        from django.conf import settings as _s

        return {
            "telegram_bot_token": getattr(_s, "TELEGRAM_BOT_TOKEN", "") or "",
            "telegram_chat_id": getattr(_s, "TELEGRAM_CHAT_ID", "") or "",
            "notify_email": getattr(_s, "PIPELINE_NOTIFY_EMAIL", "") or getattr(_s, "EMAIL_HOST_USER", "") or "",
            "smtp_host": getattr(_s, "EMAIL_HOST", "") or "",
            "smtp_user": getattr(_s, "EMAIL_HOST_USER", "") or "",
            "smtp_password": getattr(_s, "EMAIL_HOST_PASSWORD", "") or "",
            "from_email": getattr(_s, "DEFAULT_FROM_EMAIL", "") or "",
            "site_url": getattr(_s, "SITE_URL", "http://localhost:8000") or "http://localhost:8000",
        }
    except Exception:
        return {}


def _global_tg_defaults() -> tuple[str, str]:
    """Return (bot_token, chat_id) — notification config file → env → Django settings."""
    cfg = _load_notif_cfg()
    return cfg.get("telegram_bot_token") or "", cfg.get("telegram_chat_id") or ""


def _global_email_defaults() -> tuple[str, str, str, str, str]:
    """Return (to_email, smtp_host, smtp_user, smtp_password, from_email)."""
    cfg = _load_notif_cfg()
    return (
        cfg.get("notify_email") or "",
        cfg.get("smtp_host") or "",
        cfg.get("smtp_user") or "",
        cfg.get("smtp_password") or "",
        cfg.get("from_email") or "",
    )


def _global_site_url() -> str:
    cfg = _load_notif_cfg()
    return (cfg.get("site_url") or "http://localhost:8000").rstrip("/")


def _resolve_from_email(from_email: str, smtp_user: str, smtp_host: str) -> str:
    """
    If From is the default noreply@weuai.site or broken (noreply@login), SMTP rejects it.
    Use the authenticated user's real address instead.
    """
    if not from_email or "weuai.site" in from_email or "noreply@" in (from_email or "").lower():
        if not smtp_user:
            return from_email or "pipeline@noreply.local"
        user = (smtp_user or "").strip()
        if "@" in user:
            return user
        host = (smtp_host or "").lower()
        if "yandex" in host:
            return f"{user}@yandex.ru"
        if "gmail" in host:
            return f"{user}@gmail.com"
        return user
    return from_email


def _normalize_email_recipient(to_email: str, smtp_host: str) -> str:
    """If recipient is only login (no @), append domain for Yandex/Gmail."""
    to_email = (to_email or "").strip()
    if not to_email or "@" in to_email:
        return to_email
    host = (smtp_host or "").lower()
    if "yandex" in host:
        return f"{to_email}@yandex.ru"
    if "gmail" in host:
        return f"{to_email}@gmail.com"
    return to_email


async def _execute_output_telegram(node: dict, context: dict, node_outputs: dict[str, dict], run: PipelineRun) -> dict:
    """Send a message via Telegram Bot API. Falls back to TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID from .env."""
    config = node.get("data", {})
    g_token, g_chat = _global_tg_defaults()
    bot_token = (config.get("bot_token") or g_token or "").strip()
    chat_id = (config.get("chat_id") or g_chat or "").strip()

    if not bot_token:
        return {"status": "failed", "error": "bot_token not configured. Set TELEGRAM_BOT_TOKEN in .env or fill in the node."}
    if not chat_id:
        return {"status": "failed", "error": "chat_id not configured. Set TELEGRAM_CHAT_ID in .env or fill in the node."}

    message_template = config.get("message", "")
    if not message_template:
        # Auto-build message from pipeline outputs
        lines = [f"📊 *Pipeline: {run.pipeline.name}*\n"]
        for nid, state in node_outputs.items():
            out = (state.get("output") or "").strip()
            if out:
                lines.append(f"*[{nid}]*\n{out[:800]}")
        message_template = "\n\n".join(lines) or f"Pipeline {run.pipeline.name} status update."

    subs = dict(context)
    subs["all_outputs"] = "\n\n".join(
        f"[{nid}]: {(v.get('output') or '')[:500]}" for nid, v in node_outputs.items() if v.get("output")
    )
    try:
        message = message_template.format_map(subs)
    except (KeyError, ValueError):
        message = message_template

    # Telegram has 4096 char limit per message; split if needed
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    parse_mode = config.get("parse_mode", "Markdown")

    chunks = [message[i : i + 4000] for i in range(0, len(message), 4000)]
    sent = []
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            for chunk in chunks:
                payload = {"chat_id": chat_id, "text": chunk, "parse_mode": parse_mode}
                resp = await client.post(url, json=payload)
                if resp.status_code != 200:
                    err = resp.text[:200]
                    return {"status": "failed", "error": f"Telegram API error {resp.status_code}: {err}"}
                sent.append(resp.status_code)
        return {"status": "completed", "output": f"📱 Telegram message sent to {chat_id} ({len(chunks)} chunk(s))"}
    except Exception as exc:
        return {"status": "failed", "error": f"Telegram send error: {exc}"}


async def _execute_logic_wait(node: dict, context: dict, run: PipelineRun, stop_event: Event | None = None) -> dict:
    """Pause pipeline execution for a configurable number of minutes."""
    config = node.get("data", {})
    try:
        minutes = float(config.get("wait_minutes", 1))
    except (TypeError, ValueError):
        minutes = 1.0

    minutes = max(0.1, min(minutes, 1440))  # clamp: 6 seconds to 24 hours
    logger.info("logic/wait node %s: sleeping %.1f minutes", node.get("id"), minutes)
    remaining_seconds = minutes * 60
    while remaining_seconds > 0:
        if stop_event and stop_event.is_set():
            return {"status": "stopped", "output": "Wait cancelled by stop request", "stopped": True}
        fresh_status = await _s2a(
            lambda: PipelineRun.objects.filter(pk=run.pk).values_list("status", flat=True).first(),
            thread_sensitive=False,
        )()
        if fresh_status == PipelineRun.STATUS_STOPPED:
            return {"status": "stopped", "output": "Wait cancelled by stop request", "stopped": True}
        sleep_seconds = min(1.0, remaining_seconds)
        await asyncio.sleep(sleep_seconds)
        remaining_seconds -= sleep_seconds
    return {"status": "completed", "output": f"⏱️ Waited {minutes:.1f} minute(s)"}


async def _execute_logic_human_approval(
    node: dict,
    context: dict,
    node_outputs: dict[str, dict],
    run: PipelineRun,
    stop_event: Event | None = None,
) -> dict:
    """
    Pause the pipeline and wait for a human approve/reject decision.

    How it works:
    1. Generates a signed one-time token stored in node_states.
    2. Sends an email and/or Telegram message with two clickable links:
       APPROVE → GET /api/studio/runs/<run_id>/approve/<node_id>/?token=...&decision=approved
       REJECT  → GET /api/studio/runs/<run_id>/approve/<node_id>/?token=...&decision=rejected
    3. Polls the DB every 10 seconds for the decision (set by the approve endpoint).
    4. On timeout, returns failed.
    5. If approved, the pipeline continues; if rejected, the run is treated as failed
       (downstream nodes can check {node_id_status} == "failed" with a logic/condition).
    """
    config = node.get("data", {})
    node_id = node["id"]
    timeout_minutes = float(config.get("timeout_minutes", 120))

    # Global fallbacks from Django settings / env
    g_to, _gh, _gu, _gp, _gf = _global_email_defaults()
    g_token, g_chat = _global_tg_defaults()
    base_url = (config.get("base_url") or "").rstrip("/") or _global_site_url()

    # Build rich context for the notification message
    all_outputs_text = "\n\n".join(
        f"--- [{nid}] ---\n{(v.get('output') or '').strip()[:2000]}"
        for nid, v in node_outputs.items()
        if (v.get("output") or "").strip()
    )
    subs = dict(context)
    subs["all_outputs"] = all_outputs_text

    message_template = config.get(
        "message",
        "🔔 *Pipeline approval required*\n\n"
        "*Pipeline:* {pipeline_name}\n"
        "*Run ID:* {run_id}\n\n"
        "{all_outputs}\n\n"
        "Please review the plan above and approve or reject:\n\n"
        "✅ *APPROVE:* {approve_url}\n\n"
        "❌ *REJECT:* {reject_url}",
    )

    # Generate one-time token
    approval_token = secrets.token_urlsafe(32)
    approve_url = f"{base_url}/api/studio/runs/{run.pk}/approve/{node_id}/?token={approval_token}&decision=approved"
    reject_url = f"{base_url}/api/studio/runs/{run.pk}/approve/{node_id}/?token={approval_token}&decision=rejected"

    subs["pipeline_name"] = run.pipeline.name
    subs["run_id"] = str(run.pk)
    subs["approve_url"] = approve_url
    subs["reject_url"] = reject_url
    subs["all_outputs"] = all_outputs_text
    subs["timeout_minutes"] = str(int(timeout_minutes))

    try:
        message = message_template.format_map(subs)
    except (KeyError, ValueError):
        message = message_template

    # Save initial "awaiting" state with token
    await _update_node_state(
        run,
        node_id,
        {
            "status": "awaiting_approval",
            "approval_token": approval_token,
            "approve_url": approve_url,
            "reject_url": reject_url,
            "started_at": timezone.now().isoformat(),
        },
    )

    # ── Send notifications ──────────────────────────────────────────────────

    # Email notification — node config overrides global settings; subject/body from node or default
    to_email = (config.get("to_email") or g_to or "").strip()
    if to_email:
        email_subject_tpl = (config.get("email_subject") or "").strip()
        email_body_tpl = (config.get("email_body") or "").strip()
        if email_subject_tpl:
            try:
                email_subject = email_subject_tpl.format_map(subs)
            except (KeyError, ValueError):
                email_subject = email_subject_tpl
        else:
            email_subject = f"Обновление сервера: нужно ваше решение (запуск #{run.pk})"
        if email_body_tpl:
            try:
                email_body = email_body_tpl.format_map(subs)
            except (KeyError, ValueError):
                email_body = email_body_tpl
        else:
            plan_preview = (all_outputs_text or "").strip()
            if len(plan_preview) > 1200:
                plan_preview = plan_preview[:1200].rstrip() + "\n\n... (полный отчёт в логе пайплайна)"
            email_body = (
                "Здравствуйте.\n\n"
                "Пайплайн собрал план обновлений на сервере и ждёт вашего решения.\n\n"
                "——— Отчёт и план ———\n\n"
                f"{plan_preview}\n\n"
                "——— Что сделать ———\n\n"
                f"ОДОБРИТЬ: {approve_url}\n\n"
                f"ОТКЛОНИТЬ: {reject_url}\n\n"
                f"Ссылка действительна {timeout_minutes:.0f} мин.\n\n"
                "С уважением,\nWEU Pipeline"
            )
        email_node = {
            "id": f"{node_id}_approval_email",
            "data": {
                "to_email": to_email,
                "subject": email_subject,
                "body": email_body,
                "smtp_host": config.get("smtp_host") or "",
                "smtp_port": config.get("smtp_port") or "",
                "smtp_user": config.get("smtp_user") or "",
                "smtp_password": config.get("smtp_password") or "",
                "from_email": config.get("from_email") or "",
            },
        }
        try:
            await _execute_output_email(email_node, subs, node_outputs, run)
            logger.info("human_approval node %s: approval email sent to %s", node_id, to_email)
        except Exception as exc:
            logger.warning("human_approval email failed: %s", exc)

    # Telegram notification — node config overrides global settings
    tg_bot_token = (config.get("tg_bot_token") or g_token or "").strip()
    tg_chat_id = (config.get("tg_chat_id") or g_chat or "").strip()
    if tg_bot_token and tg_chat_id:
        tg_node = {
            "id": f"{node_id}_approval_tg",
            "data": {
                "bot_token": tg_bot_token,
                "chat_id": tg_chat_id,
                "message": message,
            },
        }
        try:
            await _execute_output_telegram(tg_node, subs, node_outputs, run)
            logger.info("human_approval node %s: Telegram notification sent", node_id)
        except Exception as exc:
            logger.warning("human_approval Telegram failed: %s", exc)

    # ── Poll for decision ───────────────────────────────────────────────────
    deadline = timezone.now() + timedelta(minutes=timeout_minutes)
    poll_interval = 2  # seconds

    while True:
        if stop_event and stop_event.is_set():
            return {"status": "stopped", "output": "Approval wait cancelled by stop request", "stopped": True}
        await asyncio.sleep(poll_interval)

        # Check if pipeline was stopped externally
        fresh_run = await _s2a(lambda: PipelineRun.objects.get(pk=run.pk), thread_sensitive=False)()
        if fresh_run.status == PipelineRun.STATUS_STOPPED:
            return {"status": "stopped", "output": "Approval wait cancelled by stop request", "stopped": True}

        node_state = fresh_run.node_states.get(node_id, {})
        decision = node_state.get("approval_decision")

        if decision == "approved":
            user_response = node_state.get("approval_response", "")
            logger.info("human_approval node %s: APPROVED (response: %r)", node_id, user_response[:100])
            return {
                "status": "completed",
                "output": f"APPROVED\n\nUser response:\n{user_response}" if user_response else "APPROVED",
                "approved": True,
                "user_response": user_response,
            }

        if decision == "rejected":
            user_response = node_state.get("approval_response", "")
            logger.info("human_approval node %s: REJECTED", node_id)
            return {
                "status": "failed",
                "error": f"REJECTED by user.\n\nReason: {user_response}" if user_response else "REJECTED by user.",
                "approved": False,
            }

        if timezone.now() >= deadline:
            logger.warning("human_approval node %s: TIMEOUT after %.0f min", node_id, timeout_minutes)
            return {
                "status": "failed",
                "error": f"Approval timeout — no response within {timeout_minutes:.0f} minutes",
            }


# ---------------------------------------------------------------------------
# Channel layer event helper
# ---------------------------------------------------------------------------


def _make_run_event_callback(run: PipelineRun, node_id: str):
    """Returns an async callback that forwards agent events to the pipeline run channel group."""

    async def callback(event_type: str, data: dict):
        layer = get_channel_layer()
        if layer:
            with contextlib.suppress(Exception):
                await layer.group_send(
                    f"pipeline_run_{run.pk}",
                    {
                        "type": "pipeline.node.event",
                        "node_id": node_id,
                        "event_type": event_type,
                        "data": data,
                    },
                )

    return callback


# ---------------------------------------------------------------------------
# State persistence helpers
# ---------------------------------------------------------------------------


async def _update_node_state(run: PipelineRun, node_id: str, state: dict):
    """Persist node state and notify WS clients."""
    run.node_states[node_id] = state
    logger.info(
        "pipeline run %s node %s state -> %s",
        run.pk,
        node_id,
        state.get("status", "unknown"),
    )

    await _s2a_fn(lambda: PipelineRun.objects.filter(pk=run.pk).update(node_states=run.node_states))()

    actor_ctx = _pipeline_actor_context(run)
    await log_user_activity_async(
        user_id=actor_ctx.get("user_id"),
        username_snapshot=str(actor_ctx.get("username_snapshot") or ""),
        category="pipeline",
        action="pipeline_node_state",
        status="error" if state.get("status") == "failed" else "success",
        description=f"Node {node_id} -> {state.get('status', 'unknown')}",
        entity_type="pipeline_run",
        entity_id=str(run.pk),
        entity_name=actor_ctx.get("entity_name") or "",
        metadata={
            "node_id": node_id,
            "node_status": state.get("status", "unknown"),
            "started_at": state.get("started_at"),
            "finished_at": state.get("finished_at"),
            "error": str(state.get("error") or "")[:4000],
        },
    )

    layer = get_channel_layer()
    if layer:
        with contextlib.suppress(Exception):
            await layer.group_send(
                f"pipeline_run_{run.pk}",
                {"type": "pipeline.node.state", "node_id": node_id, "state": state},
            )


async def _update_run_status(run: PipelineRun, status: str, **extra):
    run.status = status
    for k, v in extra.items():
        setattr(run, k, v)
    logger.info(
        "pipeline run %s status -> %s%s",
        run.pk,
        status,
        f" extra={list(extra.keys())}" if extra else "",
    )
    await _s2a_fn(run.save)()

    actor_ctx = _pipeline_actor_context(run)
    await log_user_activity_async(
        user_id=actor_ctx.get("user_id"),
        username_snapshot=str(actor_ctx.get("username_snapshot") or ""),
        category="pipeline",
        action="pipeline_run_status",
        status="error" if status == PipelineRun.STATUS_FAILED else "success",
        description=f"Pipeline run #{run.pk} -> {status}",
        entity_type="pipeline_run",
        entity_id=str(run.pk),
        entity_name=actor_ctx.get("entity_name") or "",
        metadata={
            "status": status,
            "extra": extra,
        },
    )

    layer = get_channel_layer()
    if layer:
        with contextlib.suppress(Exception):
            await layer.group_send(
                f"pipeline_run_{run.pk}",
                {"type": "pipeline.status", "status": status, **extra},
            )


# ---------------------------------------------------------------------------
# Main executor
# ---------------------------------------------------------------------------


class PipelineExecutor:
    """
    Executes a Pipeline by traversing nodes in topological (BFS) order.

    Usage::
        executor = PipelineExecutor(pipeline_run)
        await executor.execute(context={"key": "value"})
    """

    def __init__(self, run: PipelineRun):
        self.run = run
        self._stop_requested = False
        self._stop_event = Event()
        self._executed_mcp_tools: set[str] = set()

    def request_stop(self):
        self._stop_requested = True
        self._stop_event.set()

    async def _sync_stop_state_from_db(self) -> bool:
        run_snapshot = await _s2a_fn(
            lambda: PipelineRun.objects.filter(pk=self.run.pk).values("status", "runtime_control").first()
        )()
        if run_snapshot is None:
            self.request_stop()
            return self._stop_requested

        if run_snapshot.get("status") == PipelineRun.STATUS_STOPPED or is_runtime_stop_requested(
            run_snapshot.get("runtime_control")
        ):
            self.request_stop()
        return self._stop_requested

    async def execute(self, context: dict | None = None) -> PipelineRun:
        run = self.run
        owner = await _s2a_fn(lambda: run.pipeline.owner)()
        register_executor(run.pk, self)
        try:
            with audit_context(**_pipeline_actor_context(run)):
                if context is None:
                    context = {}
                if not isinstance(context, dict):
                    await _update_run_status(
                        run,
                        PipelineRun.STATUS_FAILED,
                        error="Pipeline run context must be a JSON object.",
                        finished_at=timezone.now(),
                    )
                    return run
                if await self._sync_stop_state_from_db():
                    await _update_run_status(run, PipelineRun.STATUS_STOPPED, finished_at=timezone.now())
                    return run
                context = dict(context)

                validation_errors = await _s2a_fn(
                    lambda: validate_pipeline_definition(
                        nodes=run.pipeline.nodes or [],
                        edges=run.pipeline.edges or [],
                        owner=owner,
                    )
                )()
                if validation_errors:
                    await _update_run_status(
                        run,
                        PipelineRun.STATUS_FAILED,
                        error=f"Pipeline validation failed: {'; '.join(validation_errors)}",
                        finished_at=timezone.now(),
                    )
                    return run
                if not any(not str(node.get("type") or "").startswith("trigger/") for node in (run.pipeline.nodes or [])):
                    await _update_run_status(
                        run,
                        PipelineRun.STATUS_FAILED,
                        error="Pipeline has no executable nodes.",
                        finished_at=timezone.now(),
                    )
                    return run

                run.nodes_snapshot = run.pipeline.nodes
                run.edges_snapshot = run.pipeline.edges
                run.context = context
                run.started_at = timezone.now()
                await _s2a_fn(run.save)()

                logger.info(
                    "pipeline run %s start: pipeline=%s context_keys=%s nodes=%s edges=%s",
                    run.pk,
                    run.pipeline.name,
                    sorted(context.keys()),
                    len(run.nodes_snapshot or []),
                    len(run.edges_snapshot or []),
                )
                await _update_run_status(run, PipelineRun.STATUS_RUNNING)

                nodes = run.nodes_snapshot
                edges = run.edges_snapshot

                layers = _topo_sort(nodes, edges)
                node_outputs: dict[str, dict] = {}

                try:
                    for layer_index, layer in enumerate(layers, start=1):
                        if await self._sync_stop_state_from_db():
                            break

                        # Filter trigger nodes — they just inject context and pass through
                        exec_nodes = [n for n in layer if not n.get("type", "").startswith("trigger/")]
                        logger.info(
                            "pipeline run %s layer %s start: nodes=%s exec_nodes=%s",
                            run.pk,
                            layer_index,
                            [n.get("id") for n in layer],
                            [n.get("id") for n in exec_nodes],
                        )

                        if not exec_nodes:
                            continue

                        # Mark all nodes in this layer as running
                        for node in exec_nodes:
                            await _update_node_state(
                                run,
                                node["id"],
                                {"status": "running", "started_at": timezone.now().isoformat()},
                            )

                        # Execute all nodes in this layer concurrently
                        tasks = [self._execute_node(node, context, node_outputs) for node in exec_nodes]
                        results = await asyncio.gather(*tasks, return_exceptions=True)

                        for node, result in zip(exec_nodes, results, strict=False):
                            nid = node["id"]
                            if isinstance(result, Exception):
                                logger.exception("pipeline run %s node %s raised exception", run.pk, nid, exc_info=result)
                                state: dict[str, Any] = {
                                    "status": "failed",
                                    "error": str(result),
                                    "finished_at": timezone.now().isoformat(),
                                }
                            else:
                                state = {**result, "finished_at": timezone.now().isoformat()}
                                if "started_at" not in state:
                                    state["started_at"] = timezone.now().isoformat()

                            node_outputs[nid] = state
                            await _update_node_state(run, nid, state)
                            logger.info(
                                "pipeline run %s node %s finished: type=%s status=%s error=%s output_chars=%s",
                                run.pk,
                                nid,
                                node.get("type", ""),
                                state.get("status"),
                                (state.get("error") or "")[:300],
                                len(state.get("output") or ""),
                            )

                            # If a critical node failed and no condition node follows, abort
                            node_type = node.get("type", "")
                            if state["status"] == "failed" and node_type.startswith("agent/"):
                                on_fail = node.get("data", {}).get("on_failure", "continue")
                                if on_fail == "abort":
                                    raise RuntimeError(f"Node {nid} failed: {state.get('error')}")

                except Exception as exc:
                    run.error = str(exc)
                    logger.exception("pipeline run %s failed", run.pk)
                    await _update_run_status(run, PipelineRun.STATUS_FAILED, error=str(exc), finished_at=timezone.now())
                    return run

                if self._stop_requested:
                    await _update_run_status(run, PipelineRun.STATUS_STOPPED, finished_at=timezone.now())
                else:
                    await _update_run_status(run, PipelineRun.STATUS_COMPLETED, finished_at=timezone.now())

                logger.info("pipeline run %s finished: status=%s", run.pk, run.status)
                return run
        finally:
            unregister_executor(run.pk, self)

    async def _execute_node(self, node: dict, context: dict, node_outputs: dict[str, dict]) -> dict:
        node_type = node.get("type", "")

        # Build enriched context: merge previous node outputs so templates like
        # {n2}, {n2_output}, {n2_error} are all available in every node.
        # Use a defaultdict so unknown keys return "" instead of raising KeyError.
        enriched: dict = defaultdict(str, context)
        for nid, state in node_outputs.items():
            out = state.get("output", "") or ""
            err = state.get("error", "") or ""
            enriched[nid] = out
            enriched[f"{nid}_output"] = out
            enriched[f"{nid}_error"] = err
            enriched[f"{nid}_status"] = state.get("status", "")

        if node_type == "agent/react":
            return await _execute_agent_react(node, enriched, self.run)

        if node_type == "agent/multi":
            return await _execute_agent_multi(node, enriched, self.run)

        if node_type == "agent/ssh_cmd":
            return await _execute_agent_ssh_cmd(node, enriched, self.run)

        if node_type == "agent/llm_query":
            return await _execute_agent_llm_query(node, enriched, node_outputs, self.run)

        if node_type == "agent/mcp_call":
            return await _execute_agent_mcp_call(node, enriched, self.run, self._executed_mcp_tools)

        if node_type == "logic/condition":
            return await _execute_logic_condition(node, enriched, node_outputs, self.run)

        if node_type == "logic/parallel":
            # Parallel node just passes through; actual parallelism is handled by BFS layer
            return {"status": "completed", "output": "parallel gateway"}

        if node_type == "logic/wait":
            return await _execute_logic_wait(node, enriched, self.run, self._stop_event)

        if node_type == "logic/human_approval":
            return await _execute_logic_human_approval(node, enriched, node_outputs, self.run, self._stop_event)

        if node_type == "output/report":
            return await _execute_output_report(node, enriched, node_outputs, self.run)

        if node_type == "output/webhook":
            return await _execute_output_webhook(node, enriched, node_outputs)

        if node_type == "output/email":
            return await _execute_output_email(node, enriched, node_outputs, self.run)

        if node_type == "output/telegram":
            return await _execute_output_telegram(node, enriched, node_outputs, self.run)

        logger.warning("Unknown node type: %s (node id=%s)", node_type, node.get("id"))
        return {"status": "skipped", "output": f"unknown node type: {node_type}"}
