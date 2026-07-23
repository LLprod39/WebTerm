from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from asgiref.sync import sync_to_async

from app.agent_kernel.domain.specs import MCPRuntimeProvider, SkillProvider
from app.agent_kernel.hooks.manager import HookManager
from app.agent_kernel.mcp_runtime import execute_mcp_binding
from app.agent_kernel.permissions.engine import PermissionEngine
from app.agent_kernel.sandbox.manager import SandboxManager
from app.agent_kernel.tools.registry import ToolRegistry
from app.plugins.agent_tools import execute_plugin_agent_tool
from app.sudo_policy import prepare_sudo_command_args
from servers.agent_tools import get_all_agent_tools


@dataclass(frozen=True)
class MultiAgentToolExecutionContext:
    session: Any
    permission_engine: PermissionEngine
    sandbox_manager: SandboxManager
    hook_manager: HookManager
    tool_registry: ToolRegistry | None
    enabled_tools: list[str]
    mcp_tools: dict[str, Any]
    disabled_mcp_tools: set[str]
    skill_provider: SkillProvider | None
    skill_policies: list[Any]
    executed_mcp_tools: set[str]
    mcp_runtime_provider: MCPRuntimeProvider | None


async def execute_multi_agent_tool(
    name: str,
    args: dict,
    *,
    context: MultiAgentToolExecutionContext,
    permission_engine: PermissionEngine | None = None,
    tool_registry: ToolRegistry | None = None,
    allowed_tool_names: list[str] | None = None,
    engine: Any = None,
) -> str:
    active_registry = tool_registry or context.tool_registry
    active_permission_engine = permission_engine or context.permission_engine
    if name == "ask_user" and bool(getattr(engine, "unattended", False)):
        if engine is not None:
            engine._policy_blocked_count = int(getattr(engine, "_policy_blocked_count", 0) or 0) + 1
        return (
            "Human input unavailable in unattended pipeline/agent run. "
            "Use logic/human_approval or logic/telegram_input nodes, "
            "or set interaction_mode=interactive on the agent node."
        )
    if allowed_tool_names is not None and name not in allowed_tool_names:
        return f"Tool '{name}' is not available to this subagent."

    spec = active_registry.get(name) if active_registry else None
    if active_registry is not None and spec is None:
        return f"Tool '{name}' is not available in the current tool slice."

    decision = active_permission_engine.evaluate(spec, args) if spec else None
    if decision and not decision.allowed:
        if engine is not None:
            engine._policy_blocked_count = int(getattr(engine, "_policy_blocked_count", 0) or 0) + 1
        return decision.reason

    prepared_args, _sudo_notes = (
        prepare_sudo_command_args(args, active_permission_engine.sudo_policy) if name == "ssh_execute" else (args, ())
    )
    args = prepared_args

    if decision and spec:
        sandbox_decision = context.sandbox_manager.validate(spec, args, decision.sandbox_profile)
        if not sandbox_decision.allowed:
            return sandbox_decision.reason

    if name in context.mcp_tools:
        return await _execute_mcp_tool(
            name,
            args,
            context,
            spec=spec,
            permission_engine=active_permission_engine,
            decision=decision,
        )

    if name in context.disabled_mcp_tools:
        return f"Tool '{name}' is disabled for this agent."

    return await _execute_builtin_tool(
        name,
        args,
        context,
        spec=spec,
        permission_engine=active_permission_engine,
        decision=decision,
    )


async def _execute_mcp_tool(
    name: str,
    args: dict,
    context: MultiAgentToolExecutionContext,
    *,
    spec: Any,
    permission_engine: PermissionEngine,
    decision: Any,
) -> str:
    binding = context.mcp_tools[name]
    if context.skill_provider is not None:
        prepared_args, policy_messages, policy_error = context.skill_provider.apply_skill_policies(
            context.skill_policies,
            binding,
            args,
            context.executed_mcp_tools,
        )
    else:
        prepared_args, policy_messages, policy_error = args, [], None

    if policy_error:
        return policy_error

    result = await execute_mcp_binding(context.mcp_runtime_provider, context.mcp_tools, name, prepared_args)
    if not result.startswith("MCP tool error"):
        context.executed_mcp_tools.add(binding.tool_name)
        if spec:
            permission_engine.record_success(spec, prepared_args, result)
    if policy_messages:
        result = "\n".join([*policy_messages, result])
    if decision and decision.notes:
        result = "\n".join([*decision.notes, result])
    return await context.hook_manager.post_tool_use(name, result)


async def _execute_builtin_tool(
    name: str,
    args: dict,
    context: MultiAgentToolExecutionContext,
    *,
    spec: Any,
    permission_engine: PermissionEngine,
    decision: Any,
) -> str:
    tool_meta = get_all_agent_tools().get(name)
    if tool_meta is None:
        return f"Unknown tool: {name}"
    if name not in context.enabled_tools:
        return f"Tool '{name}' is disabled for this agent."
    if tool_meta.get("plugin_id"):
        result = await sync_to_async(execute_plugin_agent_tool, thread_sensitive=True)(
            {
                "tool": tool_meta,
                "tool_name": name,
                "args": args,
                "user": getattr(context.session, "user", None),
            }
        )
        result_text = str(result.get("result") or result.get("error") or "")
        if spec and result.get("success"):
            permission_engine.record_success(spec, args, result_text)
        if decision and decision.notes:
            result_text = "\n".join([*decision.notes, result_text])
        return await context.hook_manager.post_tool_use(name, result_text)

    fn = tool_meta["fn"]
    try:
        result = await fn(context.session, **args)
        result_text = result.result
        if spec and result.success:
            permission_engine.record_success(spec, args, result_text)
        if decision and decision.notes:
            result_text = "\n".join([*decision.notes, result_text])
        return await context.hook_manager.post_tool_use(name, result_text)
    except Exception as exc:
        return await context.hook_manager.post_tool_use(name, f"Tool error ({name}): {exc}")
