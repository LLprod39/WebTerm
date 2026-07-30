from __future__ import annotations

import json
import logging
from typing import Any

from asgiref.sync import sync_to_async as _s2a

from app.agent_kernel.hooks.manager import HookManager
from app.agent_kernel.permissions.engine import PermissionEngine
from app.agent_kernel.sandbox.manager import SandboxManager
from app.execution_policy import safe_payload_preview
from core_ui.activity import log_user_activity_async
from studio.mcp_client import call_mcp_tool
from studio.mcp_tool_runtime import MCPBoundTool
from studio.models import MCPServerPool, PipelineRun
from studio.skill_policy import apply_skill_policies, compile_skill_policies
from studio.skill_registry import normalise_skill_slugs, resolve_skills

from .pipeline_context import (
    build_pipeline_tool_spec,
    pipeline_actor_context,
    pipeline_permission_mode,
    render_template_value,
)

logger = logging.getLogger(__name__)


def _s2a_fn(func, thread_sensitive=False):
    return _s2a(func, thread_sensitive=thread_sensitive)


def coerce_mcp_arguments(config: dict[str, Any]) -> tuple[dict[str, Any] | None, str | None]:
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


def mcp_result_to_text(result: dict[str, Any]) -> str:
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


async def execute_agent_mcp_call(
    node: dict,
    context: dict,
    run: PipelineRun,
    executed_mcp_tools: set[str] | None = None,
) -> dict:
    """Execute a direct MCP tools/call request against a configured MCP server."""
    config = node.get("data", {})
    owner = await _s2a_fn(lambda: run.pipeline.owner)()
    mcp_server_id = config.get("mcp_server_id")
    tool_name = str(config.get("tool_name") or "").strip()
    node_skill_slugs = normalise_skill_slugs(config.get("skill_slugs"))

    if not mcp_server_id:
        return {"status": "failed", "error": "Select an MCP server for this node"}
    if not tool_name:
        return {"status": "failed", "error": "Select an MCP tool for this node"}

    arguments_template, error = coerce_mcp_arguments(config)
    if error:
        return {"status": "failed", "error": error}

    try:
        mcp_server = await _s2a_fn(MCPServerPool.objects.get)(id=int(mcp_server_id), owner=owner)
    except MCPServerPool.DoesNotExist:
        return {"status": "failed", "error": f"MCP server not found: {mcp_server_id}"}
    except (TypeError, ValueError):
        return {"status": "failed", "error": f"Invalid MCP server id: {mcp_server_id}"}

    arguments = render_template_value(arguments_template or {}, context)
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
    permission_engine = PermissionEngine(mode=pipeline_permission_mode(config))
    sandbox_manager = SandboxManager()
    hook_manager = HookManager()
    spec = build_pipeline_tool_spec(f"mcp_{tool_name}")
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
            safe_payload_preview(prepared_args),
        )
        result = await call_mcp_tool(mcp_server, tool_name, prepared_args)
        output = mcp_result_to_text(result)
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
        actor_ctx = pipeline_actor_context(run)
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
        actor_ctx = pipeline_actor_context(run)
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
