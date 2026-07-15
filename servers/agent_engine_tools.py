from __future__ import annotations

import json
from typing import Any

from asgiref.sync import sync_to_async as _s2a
from loguru import logger

from app.agent_kernel.mcp_runtime import execute_mcp_binding
from app.execution_policy import safe_payload_preview
from app.plugins.agent_tools import execute_plugin_agent_tool
from app.sudo_policy import prepare_sudo_command_args
from servers.agent_tools import get_all_agent_tools


def sync_to_async(func, thread_sensitive=False):
    return _s2a(func, thread_sensitive=thread_sensitive)


async def execute_agent_tool(engine: Any, name: str, args: dict) -> str:
    logger.info("agent_run {} execute_tool start: tool={} args={}", engine.run_record.pk if engine.run_record else "?", name, safe_payload_preview(args))
    if name == "ask_user" and bool(getattr(engine, "unattended", False)):
        message = (
            "Human input unavailable in unattended pipeline/agent run. "
            "Use logic/human_approval or logic/telegram_input nodes, "
            "or set interaction_mode=interactive on the agent node."
        )
        engine._policy_blocked_count = int(getattr(engine, "_policy_blocked_count", 0) or 0) + 1
        return message

    spec = engine.tool_registry.get(name) if engine.tool_registry else None
    schema_error = engine._validate_tool_args(name, args, spec)
    if schema_error:
        logger.warning(
            "agent_run {} execute_tool schema error: tool={} error={}",
            engine.run_record.pk if engine.run_record else "?",
            name,
            schema_error,
        )
        return schema_error

    decision = engine.permission_engine.evaluate(spec, args) if spec else None
    if decision and not decision.allowed:
        engine._policy_blocked_count = int(getattr(engine, "_policy_blocked_count", 0) or 0) + 1
        # GAP 8: audit trail persistence
        try:
            from core_ui.activity import log_user_activity
            await sync_to_async(log_user_activity)(
                user=engine.user,
                category="agent_security",
                action="tool_denied",
                status="error",
                description=decision.reason,
                entity_type="agent_run",
                entity_id=engine.run_record.pk if engine.run_record else "",
                entity_name=engine.agent.name,
                metadata={"tool": name, "args": args, "mode": decision.mode, **decision.audit_metadata},
            )
        except Exception as exc:
            logger.warning("Failed to persist audit trail for tool denial: {}", exc)
        return decision.reason

    prepared_args, _sudo_notes = (
        prepare_sudo_command_args(args, engine.permission_engine.sudo_policy)
        if name == "ssh_execute"
        else (args, ())
    )
    args = prepared_args
    if decision and spec:
        sandbox_decision = engine.sandbox_manager.validate(spec, args, decision.sandbox_profile)
        if not sandbox_decision.allowed:
            return sandbox_decision.reason
    if name in engine.mcp_tools:
        binding = engine.mcp_tools[name]
        if engine._skill_provider is not None:
            prepared_args, policy_messages, policy_error = engine._skill_provider.apply_skill_policies(
                engine.skill_policies, binding, args, engine._executed_mcp_tools
            )
        else:
            prepared_args, policy_messages, policy_error = args, [], None
        if policy_error:
            return policy_error
        result = await execute_mcp_binding(engine._mcp_runtime_provider, engine.mcp_tools, name, prepared_args)
        if not result.startswith("MCP tool error"):
            engine._executed_mcp_tools.add(binding.tool_name)
            if spec:
                engine.permission_engine.record_success(spec, prepared_args, result)
        if policy_messages:
            result = "\n".join([*policy_messages, result])
        if decision and decision.notes:
            result = "\n".join([*decision.notes, result])
        result = await engine.hook_manager.post_tool_use(name, result)
        logger.info(
            "agent_run {} execute_tool done: tool={} result_chars={} via=mcp",
            engine.run_record.pk if engine.run_record else "?",
            name,
            len(result or ""),
        )
        return result
    if name in engine.disabled_mcp_tools:
        return f"Tool '{name}' is disabled for this agent."

    tool_meta = get_all_agent_tools().get(name)
    if tool_meta is None:
        return f"Unknown tool: {name}"
    if name not in engine.enabled_tools:
        return f"Tool '{name}' is disabled for this agent."
    if tool_meta.get("plugin_id"):
        result = await sync_to_async(execute_plugin_agent_tool, thread_sensitive=True)(
            {
                "tool": tool_meta,
                "tool_name": name,
                "args": args,
                "user": engine.user,
                "agent_run_id": engine.run_record.pk if engine.run_record else None,
            }
        )
        result_text = str(result.get("result") or result.get("error") or "")
        if spec and result.get("success"):
            engine.permission_engine.record_success(spec, args, result_text)
        if decision and decision.notes:
            result_text = "\n".join([*decision.notes, result_text])
        return await engine.hook_manager.post_tool_use(name, result_text)

    fn = tool_meta["fn"]
    try:
        result = await fn(engine.session, **args)
        result_text = result.result
        if name == "ssh_execute":
            await _record_agent_ssh_history(engine, args=args, result=result)
        if spec and result.success:
            engine.permission_engine.record_success(spec, args, result_text)
        if decision and decision.notes:
            result_text = "\n".join([*decision.notes, result_text])
        result_text = await engine.hook_manager.post_tool_use(name, result_text)
        logger.info(
            "agent_run {} execute_tool done: tool={} result_chars={} via=agent_tool",
            engine.run_record.pk if engine.run_record else "?",
            name,
            len(result_text or ""),
        )
        return result_text
    except Exception as exc:
        logger.exception(
            "agent_run {} execute_tool failed: tool={}",
            engine.run_record.pk if engine.run_record else "?",
            name,
        )
        return await engine.hook_manager.post_tool_use(name, f"Tool error ({name}): {exc}")


async def _record_agent_ssh_history(engine: Any, *, args: dict, result: Any) -> None:
    """Attribute agent SSH commands to agent_run / pipeline_run / user."""
    try:
        from app.command_history_provider import save_command_history_entry
        from servers.models import ServerCommandHistory

        server_ref = str(args.get("server") or "")
        command = str(args.get("command") or "")
        if not command:
            return
        sid = None
        if engine.session is not None:
            sid = engine.session.resolve_server(server_ref)
        if sid is None:
            return
        exit_code = None
        if getattr(result, "data", None):
            exit_code = result.data.get("exit_code")
        agent_run_id = getattr(engine.run_record, "pk", None)
        pipeline_run_id = getattr(engine, "pipeline_run_id", None)
        session_id = f"agent_run:{agent_run_id or 0}"
        if pipeline_run_id:
            session_id = f"{session_id}|pipeline_run:{pipeline_run_id}"
        await sync_to_async(save_command_history_entry, thread_sensitive=True)(
            server_id=int(sid),
            user_id=getattr(engine.user, "id", None),
            command=command,
            output=str(getattr(result, "result", "") or "")[:10000],
            exit_code=exit_code,
            session_id=session_id,
            cwd="",
            actor_kind=getattr(ServerCommandHistory, "ACTOR_AGENT", "agent"),
            source_kind=getattr(ServerCommandHistory, "SOURCE_AGENT", "agent"),
        )
    except Exception as exc:
        logger.warning("Failed to record agent SSH command history: {}", exc)


def validate_agent_tool_args(name: str, args: dict, spec) -> str:
    if not isinstance(args, dict):
        return (
            f"Tool input error ({name}): ACTION arguments must be a JSON object. "
            "Repeat the action with valid JSON arguments."
        )

    schema = getattr(spec, "input_schema", None) or {}
    missing = [
        param_name
        for param_name, param_info in schema.items()
        if param_info.get("required") and args.get(param_name) in (None, "")
    ]
    if not missing:
        return ""

    required = ", ".join(missing)
    example_args = {
        param_name: f"<{param_name}>"
        for param_name, param_info in schema.items()
        if param_info.get("required")
    }
    example_json = json.dumps(example_args, ensure_ascii=False)
    return (
        f"Tool input error ({name}): missing required parameter(s): {required}. "
        f"Repeat exactly as ACTION: {name} {example_json}"
    )
