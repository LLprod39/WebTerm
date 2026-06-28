from __future__ import annotations

import json
from typing import Any

from asgiref.sync import sync_to_async as _s2a
from loguru import logger

from app.agent_kernel.mcp_runtime import execute_mcp_binding
from app.plugins.agent_tools import execute_plugin_agent_tool
from app.execution_policy import safe_payload_preview
from app.sudo_policy import prepare_sudo_command_args
from servers.agent_tools import get_all_agent_tools


def sync_to_async(func, thread_sensitive=False):
    return _s2a(func, thread_sensitive=thread_sensitive)


async def execute_agent_tool(engine: Any, name: str, args: dict) -> str:
    logger.info("agent_run {} execute_tool start: tool={} args={}", engine.run_record.pk if engine.run_record else "?", name, safe_payload_preview(args))
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
