from __future__ import annotations

import contextlib
import logging
from typing import Any

from asgiref.sync import sync_to_async as _s2a

from app.agent_kernel.hooks.manager import HookManager
from app.agent_kernel.permissions.engine import PermissionEngine
from app.agent_kernel.sandbox.manager import SandboxManager
from app.command_history_provider import save_command_history_entry
from app.core.model_utils import resolve_provider_and_model
from app.pipeline_agent_provider import run_pipeline_multi_agent, run_pipeline_react_agent
from app.pipeline_ssh_provider import get_server_connect_kwargs, get_server_sudo_password
from app.sudo_policy import prepare_sudo_command, resolve_sudo_policy
from core_ui.activity import log_user_activity_async

from .models import MCPServerPool, PipelineRun
from .pipeline_context import (
    build_pipeline_tool_spec,
    merge_unique_strings,
    pipeline_actor_context,
    pipeline_permission_mode,
    render_template_value,
)
from .pipeline_run_state import make_run_event_callback
from .services import get_owned_server, get_owned_servers_by_ids
from .skill_registry import normalise_skill_slugs, resolve_skills

logger = logging.getLogger(__name__)


def _s2a_fn(func, thread_sensitive: bool = False):
    return _s2a(func, thread_sensitive=thread_sensitive)


def _save_server_command_history(*, server_id: int, user_id: int | None, command: str, output: str, exit_code: int | None) -> None:
    save_command_history_entry(
        server_id=server_id,
        user_id=user_id,
        command=command,
        output=output,
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
    actor_ctx = pipeline_actor_context(run)
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


async def _load_owned_servers(owner, server_ids: list[int]):
    if not server_ids:
        return []
    return await _s2a_fn(get_owned_servers_by_ids)(owner, server_ids, order_by="-updated_at")


def _coerce_optional_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _resolve_context_value(config: dict[str, Any], context: dict[str, Any], field: str, default_key: str) -> Any:
    direct = config.get(field)
    if direct not in (None, ""):
        return render_template_value(direct, context) if isinstance(direct, str) else direct
    key = str(config.get(f"{field}_context_key") or default_key).strip()
    return context.get(key) if key else ""


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


async def execute_agent_react(node: dict, context: dict, run: PipelineRun) -> dict:
    """Execute an agent/react node using AgentEngine."""
    config = node.get("data", {})
    node_id = node.get("id")
    agent_config_id = config.get("agent_config_id")
    server_ids = config.get("server_ids", [])
    mcp_server_ids = config.get("mcp_server_ids", [])
    node_skill_slugs = normalise_skill_slugs(config.get("skill_slugs"))
    goal = config.get("goal", "")
    owner = await _s2a_fn(lambda: run.pipeline.owner)()

    goal = render_template_value(goal, context)
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
        max_iterations = agent_conf.max_iterations
        model = agent_conf.model
        tools_config = dict.fromkeys(agent_conf.allowed_tools or [], True)
        mcp_servers = await _s2a_fn(lambda: list(agent_conf.mcp_servers.filter(owner=owner)))()
        skill_slugs = merge_unique_strings(list(agent_conf.skill_slugs or []), node_skill_slugs)
        sudo_policy = resolve_sudo_policy(config.get("sudo_policy"), inherited=getattr(agent_conf, "sudo_policy", "disabled"))
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
        max_iterations = config.get("max_iterations", 10)
        model = config.get("model", "gemini-2.0-flash-exp")
        tools_config = dict.fromkeys(config.get("allowed_tools", []) or [], True)
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
        return {"status": "failed", "error": "Configure at least one server, one MCP server, or one skill for this agent node"}

    model_preference, specific_model = resolve_provider_and_model(
        config.get("provider"),
        model,
        default_provider="auto",
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
    )
    logger.info(
        "pipeline run %s node %s agent/react done: agent_run_id=%s status=%s report_chars=%s",
        run.pk,
        node_id,
        agent_run.agent_run_id,
        agent_run.status,
        len(agent_run.final_report or ""),
    )
    return {
        "status": "completed" if agent_run.status == "completed" else "failed",
        "agent_run_id": agent_run.agent_run_id,
        "output": agent_run.final_report or "",
        "error": agent_run.ai_analysis if agent_run.status != "completed" else "",
    }


async def execute_agent_multi(node: dict, context: dict, run: PipelineRun) -> dict:
    """Execute an agent/multi node using MultiAgentEngine."""
    config = node.get("data", {})
    server_ids = config.get("server_ids", [])
    mcp_server_ids = config.get("mcp_server_ids", [])
    node_skill_slugs = normalise_skill_slugs(config.get("skill_slugs"))
    goal = config.get("goal", "")
    owner = await _s2a_fn(lambda: run.pipeline.owner)()

    goal = render_template_value(goal, context)
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
        system_prompt = render_template_value(agent_conf.system_prompt, context)
        max_iterations = agent_conf.max_iterations
        model = agent_conf.model
        tools_config = dict.fromkeys(agent_conf.allowed_tools or [], True)
        mcp_servers = await _s2a_fn(lambda: list(agent_conf.mcp_servers.filter(owner=owner)))()
        skill_slugs = merge_unique_strings(list(agent_conf.skill_slugs or []), node_skill_slugs)
        sudo_policy = resolve_sudo_policy(config.get("sudo_policy"), inherited=getattr(agent_conf, "sudo_policy", "disabled"))
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
        max_iterations = config.get("max_iterations", 20)
        model = config.get("model", "gemini-2.0-flash-exp")
        tools_config = dict.fromkeys(config.get("allowed_tools", []) or [], True)
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

    model_preference, specific_model = resolve_provider_and_model(
        config.get("provider"),
        model,
        default_provider="auto",
    )

    agent_run = await run_pipeline_multi_agent(
        node_id=str(node["id"]),
        goal=goal,
        system_prompt=system_prompt,
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
    )
    return {
        "status": "completed" if agent_run.status == "completed" else "failed",
        "agent_run_id": agent_run.agent_run_id,
        "output": agent_run.final_report or "",
        "error": agent_run.ai_analysis if agent_run.status != "completed" else "",
    }


async def execute_agent_ssh_cmd(node: dict, context: dict, run: PipelineRun) -> dict:
    """Execute a direct SSH command without LLM."""
    import asyncssh

    config = node.get("data", {})
    raw_server_id = _resolve_context_value(config, context, "server_id", "server_id")
    server_id = _coerce_optional_int(raw_server_id)
    command = config.get("command", "")
    preflight_commands = list(config.get("preflight_commands") or [])
    verification_commands = list(config.get("verification_commands") or [])

    with contextlib.suppress(KeyError, ValueError):
        command = command.format(**context)

    if not server_id:
        if raw_server_id not in (None, ""):
            return {
                "status": "failed",
                "error": f"Invalid server_id for this SSH node: {raw_server_id!r}.",
                "output": "",
            }
        return {
            "status": "failed",
            "error": "No server configured for this SSH node. Select a Server or provide server_id in runtime context.",
            "output": "",
        }
    if not command:
        if config.get("agent_config_id") or config.get("goal"):
            patched_node = dict(node)
            patched_data = dict(config)
            if server_id and not patched_data.get("server_ids"):
                patched_data["server_ids"] = [server_id]
            patched_node["data"] = patched_data
            return await execute_agent_react(patched_node, context, run)
        return {
            "status": "failed",
            "error": "Команда не задана. Откройте узел в редакторе и введите команду в поле «Command», "
            "или смените тип узла на «ReAct Agent» если нужен ИИ-агент.",
        }

    owner = await _s2a_fn(lambda: run.pipeline.owner)()
    server = await _s2a_fn(get_owned_server)(owner, server_id)
    if server is None:
        return {"status": "failed", "error": f"Server not found: {server_id}"}

    permission_engine = PermissionEngine(
        mode=pipeline_permission_mode(config),
        sudo_policy=resolve_sudo_policy(config.get("sudo_policy")),
    )
    sandbox_manager = SandboxManager()
    hook_manager = HookManager()
    spec = build_pipeline_tool_spec("ssh_execute", command=command)
    decision = permission_engine.evaluate(spec, {"command": command})
    if not decision.allowed and not preflight_commands:
        return {
            "status": "failed",
            "error": decision.reason,
            "output": "",
        }

    try:
        connect_kwargs = await get_server_connect_kwargs(server, connect_timeout=30)
        sudo_password = await _s2a_fn(get_server_sudo_password, thread_sensitive=True)(server)

        async with asyncssh.connect(**connect_kwargs) as conn:
            combined_outputs: list[str] = []

            async def _run_remote_command(command_text: str, *, stage: str) -> tuple[int, str]:
                stage_spec = build_pipeline_tool_spec("ssh_execute", command=command_text)
                stage_decision = permission_engine.evaluate(stage_spec, {"command": command_text})
                if not stage_decision.allowed:
                    raise RuntimeError(stage_decision.reason)
                prepared_sudo = prepare_sudo_command(
                    command_text,
                    permission_engine.sudo_policy,
                    sudo_auth_mode=getattr(server, "sudo_auth_mode", "none"),
                    sudo_password=sudo_password,
                )
                executable_command = prepared_sudo.command
                sudo_notes = prepared_sudo.notes
                stage_profile = stage_decision.sandbox_profile if stage == "command" else "ops_read"
                sandbox_decision = sandbox_manager.validate(stage_spec, {"command": executable_command}, stage_profile)
                if not sandbox_decision.allowed:
                    raise RuntimeError(sandbox_decision.reason)
                run_kwargs: dict[str, Any] = {"timeout": 120}
                if prepared_sudo.input_text is not None:
                    run_kwargs["input"] = prepared_sudo.input_text
                remote_result = await conn.run(executable_command, **run_kwargs)
                remote_output = remote_result.stdout + (("\n" + remote_result.stderr) if remote_result.stderr else "")
                if sudo_notes:
                    remote_output = "\n".join(sudo_notes) + "\n" + remote_output
                compacted_output = await hook_manager.post_tool_use("ssh_execute", remote_output)
                permission_engine.record_success(stage_spec, {"command": executable_command}, compacted_output)
                await _log_pipeline_ssh_command(
                    run=run,
                    server=server,
                    node_id=str(node.get("id") or ""),
                    command=f"[{stage}] {executable_command}",
                    exit_code=remote_result.exit_status,
                    output=compacted_output,
                )
                combined_outputs.append(f"## {stage}\n{compacted_output}")
                return remote_result.exit_status, compacted_output

            for preflight_command in preflight_commands:
                rendered = render_template_value(preflight_command, context)
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
                    rendered = render_template_value(verify_command, context)
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
