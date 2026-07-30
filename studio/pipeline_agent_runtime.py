from __future__ import annotations

import logging

from app.agent_kernel.hooks.manager import HookManager
from app.agent_kernel.permissions.engine import PermissionEngine
from app.agent_kernel.runtime.outcomes import map_agent_outcome_to_pipeline_state
from app.agent_kernel.sandbox.manager import SandboxManager
from app.pipeline_agent_provider import run_pipeline_multi_agent, run_pipeline_react_agent
from app.pipeline_ssh_provider import get_server_connect_kwargs, get_server_sudo_password
from app.sudo_policy import prepare_sudo_command, resolve_sudo_policy
from core_ui.activity import log_user_activity_async
from studio.execution_policy import build_execution_policy_decisions
from studio.ops_controls import assert_agents_not_paused

from .models import MCPServerPool, PipelineRun
from .pipeline_agent_config import (
    default_max_iterations,
    is_unattended_mode,
    require_all_servers_enabled,
    resolve_agent_model_preference,
    resolve_tools_config,
)
from .pipeline_agent_runtime_helpers import (
    _coerce_optional_int,
    _load_agent_scope_ids,
    _load_owned_agent_config,
    _load_owned_servers,
    _log_pipeline_ssh_command,
    _pipeline_trigger_type,
    _resolve_context_value,
    _s2a_fn,
    _save_server_command_history,
)
from .pipeline_agent_runtime_ssh import execute_agent_ssh_cmd
from .pipeline_context import (
    build_agent_upstream_context,
    inject_upstream_into_goal,
    merge_unique_strings,
    pipeline_permission_mode,
    render_template_value,
    require_agent_goal,
)
from .pipeline_run_state import make_run_event_callback
from .skill_registry import normalise_skill_slugs, resolve_skills

logger = logging.getLogger(__name__)

# Re-export helpers and SSH deps for stable monkeypatch / import paths.
__all__ = [
    "HookManager",
    "PermissionEngine",
    "SandboxManager",
    "_coerce_optional_int",
    "_load_agent_scope_ids",
    "_load_owned_agent_config",
    "_load_owned_servers",
    "_log_pipeline_ssh_command",
    "_pipeline_trigger_type",
    "_resolve_context_value",
    "_s2a_fn",
    "_save_server_command_history",
    "execute_agent_multi",
    "execute_agent_react",
    "execute_agent_ssh_cmd",
    "get_server_connect_kwargs",
    "get_server_sudo_password",
    "log_user_activity_async",
    "prepare_sudo_command",
    "resolve_sudo_policy",
    "run_pipeline_multi_agent",
    "run_pipeline_react_agent",
]


def _node_execution_approval_granted(run: PipelineRun, node_id: str) -> bool:
    decisions = build_execution_policy_decisions(
        nodes=list(run.nodes_snapshot or []),
        edges=list(run.edges_snapshot or []),
    )
    return any(
        decision.node_id == str(node_id) and decision.requires_approval and decision.allowed for decision in decisions
    )


async def execute_agent_react(
    node: dict,
    context: dict,
    run: PipelineRun,
    node_outputs: dict[str, dict] | None = None,
) -> dict:
    """Execute an agent/react node using AgentEngine."""
    paused_error = assert_agents_not_paused()
    if paused_error:
        return {"status": "failed", "error": paused_error, "output": ""}

    config = node.get("data", {})
    node_id = node.get("id")
    agent_config_id = config.get("agent_config_id")
    server_ids = config.get("server_ids", [])
    mcp_server_ids = config.get("mcp_server_ids", [])
    node_skill_slugs = normalise_skill_slugs(config.get("skill_slugs"))
    goal = config.get("goal", "")
    owner = await _s2a_fn(lambda: run.pipeline.owner)()
    trigger_type = _pipeline_trigger_type(run)
    unattended = is_unattended_mode(config, trigger_type=trigger_type)

    goal = render_template_value(goal, context)
    upstream = build_agent_upstream_context(config, node_outputs)
    goal = inject_upstream_into_goal(goal, upstream)
    goal_error = require_agent_goal(goal)
    if goal_error:
        return {"status": "failed", "error": goal_error, "output": ""}
    servers = await _load_owned_servers(owner, server_ids) if server_ids else []

    if agent_config_id:
        try:
            agent_conf_pk = int(agent_config_id)
        except (TypeError, ValueError):
            return {"status": "failed", "error": f"Invalid agent config id: {agent_config_id}"}
        agent_conf = await _load_owned_agent_config(owner, agent_conf_pk)
        if agent_conf is None:
            return {"status": "failed", "error": f"Agent config not found: {agent_config_id}"}
        system_prompt = render_template_value(agent_conf.system_prompt, context)
        instructions = render_template_value(agent_conf.instructions, context)
        max_iterations = agent_conf.max_iterations or default_max_iterations("agent/react")
        model = agent_conf.model
        tools_source = {
            **config,
            "allowed_tools": list(agent_conf.allowed_tools or config.get("allowed_tools") or []),
            "tools_mode": config.get("tools_mode") or ("allowlist" if agent_conf.allowed_tools else "all"),
        }
        tools_config, tools_error = resolve_tools_config(tools_source)
        if tools_error:
            return {"status": "failed", "error": tools_error, "output": ""}
        mcp_servers = await _s2a_fn(lambda: list(agent_conf.mcp_servers.filter(owner=owner)))()
        skill_slugs = merge_unique_strings(list(agent_conf.skill_slugs or []), node_skill_slugs)
        sudo_policy = resolve_sudo_policy(
            config.get("sudo_policy"), inherited=getattr(agent_conf, "sudo_policy", "disabled")
        )
        allowed_server_ids = await _load_agent_scope_ids(agent_conf)
        if allowed_server_ids:
            disallowed = [server_id for server_id in server_ids if server_id not in allowed_server_ids]
            if disallowed:
                return {
                    "status": "failed",
                    "error": f"Node references servers outside agent scope: {disallowed}",
                }
    else:
        system_prompt = render_template_value(config.get("system_prompt", ""), context)
        instructions = render_template_value(config.get("instructions", ""), context)
        max_iterations = config.get("max_iterations") or default_max_iterations("agent/react")
        model = config.get("model") or ""
        tools_config, tools_error = resolve_tools_config(config)
        if tools_error:
            return {"status": "failed", "error": tools_error, "output": ""}
        mcp_servers = (
            await _s2a_fn(lambda: list(MCPServerPool.objects.filter(id__in=mcp_server_ids, owner=owner)))()
            if mcp_server_ids
            else []
        )
        skill_slugs = node_skill_slugs
        sudo_policy = resolve_sudo_policy(config.get("sudo_policy"))

    skills, skill_errors = resolve_skills(skill_slugs)

    if server_ids and not servers:
        return {"status": "failed", "error": f"Servers not found: {server_ids}"}
    if not servers and not mcp_servers and not skills:
        return {
            "status": "failed",
            "error": "Configure at least one server, one MCP server, or one skill for this agent node",
        }
    if server_ids and require_all_servers_enabled(config, default=False) and len(servers) < len(server_ids):
        found_ids = {int(s.id) for s in servers}
        missing = [sid for sid in server_ids if int(sid) not in found_ids]
        return {
            "status": "failed",
            "error": f"require_all_servers: missing servers {missing}",
            "output": "",
        }

    model_preference, specific_model = resolve_agent_model_preference(config, model=model)

    logger.info(
        "pipeline run %s node %s agent/react start: provider=%s model=%s servers=%s mcp_servers=%s skills=%s unattended=%s",
        run.pk,
        node_id,
        model_preference,
        specific_model,
        [srv.name for srv in servers],
        [srv.name for srv in mcp_servers],
        [skill.slug for skill in skills],
        unattended,
    )

    agent_run = await run_pipeline_react_agent(
        node_id=str(node["id"]),
        goal=goal,
        system_prompt=system_prompt,
        instructions=instructions,
        max_iterations=max_iterations,
        tools_config=tools_config,
        servers=servers,
        user=owner,
        event_callback=make_run_event_callback(run, node["id"]),
        model_preference=model_preference,
        specific_model=specific_model,
        mcp_servers=mcp_servers,
        skills=skills,
        skill_errors=skill_errors,
        permission_mode=pipeline_permission_mode(config),
        sudo_policy=sudo_policy,
        unattended=unattended,
        pipeline_run_id=run.pk,
        require_all_servers=require_all_servers_enabled(config, default=False),
        execution_approval_granted=_node_execution_approval_granted(run, str(node["id"])),
    )
    logger.info(
        "pipeline run %s node %s agent/react done: agent_run_id=%s status=%s outcome=%s report_chars=%s",
        run.pk,
        node_id,
        agent_run.agent_run_id,
        agent_run.status,
        getattr(agent_run, "outcome", "") or "",
        len(agent_run.final_report or ""),
    )
    state = map_agent_outcome_to_pipeline_state(
        outcome=getattr(agent_run, "outcome", "") or "",
        agent_status=agent_run.status,
        final_report=agent_run.final_report or "",
        ai_analysis=agent_run.ai_analysis or "",
        agent_run_id=agent_run.agent_run_id,
        on_partial=config.get("on_partial"),
        tool_call_count=int(getattr(agent_run, "tool_call_count", 0) or 0),
        failed_task_count=int(getattr(agent_run, "failed_task_count", 0) or 0),
        verification_summary=str(getattr(agent_run, "verification_summary", "") or ""),
        plan_summary=dict(getattr(agent_run, "plan_summary", None) or {}),
        outcome_reason=str(getattr(agent_run, "outcome_reason", "") or ""),
    )
    state["policy_blocked_count"] = int(getattr(agent_run, "policy_blocked_count", 0) or 0)
    state["disconnected_servers"] = list(getattr(agent_run, "disconnected_servers", None) or [])
    return state


async def execute_agent_multi(
    node: dict,
    context: dict,
    run: PipelineRun,
    node_outputs: dict[str, dict] | None = None,
) -> dict:
    """Execute an agent/multi node using MultiAgentEngine."""
    paused_error = assert_agents_not_paused()
    if paused_error:
        return {"status": "failed", "error": paused_error, "output": ""}

    config = node.get("data", {})
    server_ids = config.get("server_ids", [])
    mcp_server_ids = config.get("mcp_server_ids", [])
    node_skill_slugs = normalise_skill_slugs(config.get("skill_slugs"))
    goal = config.get("goal", "")
    owner = await _s2a_fn(lambda: run.pipeline.owner)()
    trigger_type = _pipeline_trigger_type(run)
    unattended = is_unattended_mode(config, trigger_type=trigger_type)

    goal = render_template_value(goal, context)
    upstream = build_agent_upstream_context(config, node_outputs)
    goal = inject_upstream_into_goal(goal, upstream)
    goal_error = require_agent_goal(goal)
    if goal_error:
        return {"status": "failed", "error": goal_error, "output": ""}
    servers = await _load_owned_servers(owner, server_ids) if server_ids else []

    agent_config_id = config.get("agent_config_id")
    instructions = ""
    if agent_config_id:
        try:
            agent_conf_pk = int(agent_config_id)
        except (TypeError, ValueError):
            return {"status": "failed", "error": f"Invalid agent config id: {agent_config_id}"}
        agent_conf = await _load_owned_agent_config(owner, agent_conf_pk)
        if agent_conf is None:
            return {"status": "failed", "error": f"Agent config not found: {agent_config_id}"}
        system_prompt = render_template_value(agent_conf.system_prompt, context)
        instructions = render_template_value(agent_conf.instructions, context)
        max_iterations = agent_conf.max_iterations or default_max_iterations("agent/multi")
        model = agent_conf.model
        tools_source = {
            **config,
            "allowed_tools": list(agent_conf.allowed_tools or config.get("allowed_tools") or []),
            "tools_mode": config.get("tools_mode") or ("allowlist" if agent_conf.allowed_tools else "all"),
        }
        tools_config, tools_error = resolve_tools_config(tools_source)
        if tools_error:
            return {"status": "failed", "error": tools_error, "output": ""}
        mcp_servers = await _s2a_fn(lambda: list(agent_conf.mcp_servers.filter(owner=owner)))()
        skill_slugs = merge_unique_strings(list(agent_conf.skill_slugs or []), node_skill_slugs)
        sudo_policy = resolve_sudo_policy(
            config.get("sudo_policy"), inherited=getattr(agent_conf, "sudo_policy", "disabled")
        )
        allowed_server_ids = await _load_agent_scope_ids(agent_conf)
        if allowed_server_ids:
            disallowed = [server_id for server_id in server_ids if server_id not in allowed_server_ids]
            if disallowed:
                return {
                    "status": "failed",
                    "error": f"Node references servers outside agent scope: {disallowed}",
                }
    else:
        system_prompt = render_template_value(config.get("system_prompt", ""), context)
        instructions = render_template_value(config.get("instructions", ""), context)
        max_iterations = config.get("max_iterations") or default_max_iterations("agent/multi")
        model = config.get("model") or ""
        tools_config, tools_error = resolve_tools_config(config)
        if tools_error:
            return {"status": "failed", "error": tools_error, "output": ""}
        mcp_servers = (
            await _s2a_fn(lambda: list(MCPServerPool.objects.filter(id__in=mcp_server_ids, owner=owner)))()
            if mcp_server_ids
            else []
        )
        skill_slugs = node_skill_slugs
        sudo_policy = resolve_sudo_policy(config.get("sudo_policy"))

    skills, skill_errors = resolve_skills(skill_slugs)

    if server_ids and not servers:
        return {"status": "failed", "error": f"Servers not found: {server_ids}"}
    if not servers and not mcp_servers and not skills:
        return {
            "status": "failed",
            "error": "Configure at least one server, one MCP server, or one skill for this multi agent node",
        }
    if server_ids and require_all_servers_enabled(config, default=True) and len(servers) < len(server_ids):
        found_ids = {int(s.id) for s in servers}
        missing = [sid for sid in server_ids if int(sid) not in found_ids]
        return {
            "status": "failed",
            "error": f"require_all_servers: missing servers {missing}",
            "output": "",
        }

    model_preference, specific_model = resolve_agent_model_preference(config, model=model)

    agent_run = await run_pipeline_multi_agent(
        node_id=str(node["id"]),
        goal=goal,
        system_prompt=system_prompt,
        instructions=instructions,
        max_iterations=max_iterations,
        tools_config=tools_config,
        servers=servers,
        user=owner,
        event_callback=make_run_event_callback(run, node["id"]),
        model_preference=model_preference,
        specific_model=specific_model,
        mcp_servers=mcp_servers,
        skills=skills,
        skill_errors=skill_errors,
        permission_mode=pipeline_permission_mode(config),
        sudo_policy=sudo_policy,
        unattended=unattended,
        pipeline_run_id=run.pk,
        require_all_servers=require_all_servers_enabled(config, default=True),
        execution_approval_granted=_node_execution_approval_granted(run, str(node["id"])),
    )
    state = map_agent_outcome_to_pipeline_state(
        outcome=getattr(agent_run, "outcome", "") or "",
        agent_status=agent_run.status,
        final_report=agent_run.final_report or "",
        ai_analysis=agent_run.ai_analysis or "",
        agent_run_id=agent_run.agent_run_id,
        on_partial=config.get("on_partial"),
        tool_call_count=int(getattr(agent_run, "tool_call_count", 0) or 0),
        failed_task_count=int(getattr(agent_run, "failed_task_count", 0) or 0),
        verification_summary=str(getattr(agent_run, "verification_summary", "") or ""),
        plan_summary=dict(getattr(agent_run, "plan_summary", None) or {}),
        outcome_reason=str(getattr(agent_run, "outcome_reason", "") or ""),
    )
    state["policy_blocked_count"] = int(getattr(agent_run, "policy_blocked_count", 0) or 0)
    state["disconnected_servers"] = list(getattr(agent_run, "disconnected_servers", None) or [])
    return state
