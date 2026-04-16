from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from loguru import logger

from studio.mcp_client import call_mcp_tool, list_mcp_tools
from studio.models import MCPServerPool


@dataclass(slots=True)
class MCPBoundTool:
    action_name: str
    server: MCPServerPool
    tool_name: str
    description: str
    input_schema: dict[str, Any] | None


def _slugify(value: str, fallback: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", (value or "").lower()).strip("_")
    return slug or fallback


def _unique_action_name(server: MCPServerPool, tool_name: str, taken: set[str], index: int) -> str:
    base = f"mcp_{_slugify(server.name, f'server_{server.id}')}_{_slugify(tool_name, f'tool_{index}')}"
    candidate = base
    suffix = 2
    while candidate in taken:
        candidate = f"{base}_{suffix}"
        suffix += 1
    taken.add(candidate)
    return candidate


def _schema_parameters_text(input_schema: dict[str, Any] | None) -> str:
    if not isinstance(input_schema, dict):
        return "  - No parameters"

    properties = input_schema.get("properties") or {}
    if not isinstance(properties, dict) or not properties:
        return "  - No parameters"

    required = input_schema.get("required") or []
    required_set = {str(item) for item in required if isinstance(item, str)}
    lines: list[str] = []
    for name, info in properties.items():
        if not isinstance(info, dict):
            lines.append(f"  - {name}: any")
            continue
        type_name = str(info.get("type") or "any")
        description = str(info.get("description") or "").strip()
        required_suffix = " (required)" if name in required_set else ""
        line = f"  - {name}: {type_name}{required_suffix}"
        if description:
            line += f" — {description}"
        lines.append(line)
    return "\n".join(lines) if lines else "  - No parameters"


def build_mcp_tools_description(bindings: dict[str, MCPBoundTool]) -> str:
    if not bindings:
        return ""

    sections = ["### MCP tools"]
    for binding in bindings.values():
        summary = binding.description.strip() if binding.description else "Call an attached MCP tool."
        params = _schema_parameters_text(binding.input_schema)
        sections.append(
            "\n".join(
                [
                    f"### {binding.action_name}",
                    f"MCP server: {binding.server.name}",
                    f"Original MCP tool: {binding.tool_name}",
                    summary,
                    "Parameters:",
                    params,
                ]
            )
        )
    return "\n\n".join(sections)


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


async def load_mcp_tool_bindings(mcp_servers: list[MCPServerPool]) -> tuple[dict[str, MCPBoundTool], list[str]]:
    bindings: dict[str, MCPBoundTool] = {}
    errors: list[str] = []
    taken_names: set[str] = set()

    for server_index, server in enumerate(mcp_servers, start=1):
        try:
            tools = await list_mcp_tools(server)
        except Exception as exc:
            logger.warning("Failed to inspect MCP server {} ({}): {}", server.name, server.id, exc)
            errors.append(f"{server.name}: {exc}")
            continue

        for tool_index, tool in enumerate(tools, start=1):
            tool_name = str(tool.get("name") or "").strip()
            if not tool_name:
                continue
            action_name = _unique_action_name(server, tool_name, taken_names, server_index * 100 + tool_index)
            bindings[action_name] = MCPBoundTool(
                action_name=action_name,
                server=server,
                tool_name=tool_name,
                description=str(tool.get("description") or ""),
                input_schema=tool.get("inputSchema") if isinstance(tool.get("inputSchema"), dict) else None,
            )

    return bindings, errors


async def execute_bound_mcp_tool(bindings: dict[str, MCPBoundTool], action_name: str, args: dict[str, Any]) -> str:
    binding = bindings.get(action_name)
    if binding is None:
        return f"Unknown MCP tool: {action_name}"
    if not isinstance(args, dict):
        return "MCP tool arguments must be a JSON object."

    try:
        logger.info(
            "mcp bound tool start: action={} server={} tool={} args={}",
            action_name,
            binding.server.name,
            binding.tool_name,
            json.dumps(args, ensure_ascii=False)[:1000],
        )
        result = await call_mcp_tool(binding.server, binding.tool_name, args)
    except Exception as exc:
        logger.exception(
            "mcp bound tool failed: action={} server={} tool={}",
            action_name,
            binding.server.name,
            binding.tool_name,
        )
        return f"MCP tool error ({binding.server.name}/{binding.tool_name}): {exc}"

    output = _mcp_result_to_text(result)
    logger.info(
        "mcp bound tool done: action={} server={} tool={} is_error={} output_chars={}",
        action_name,
        binding.server.name,
        binding.tool_name,
        bool(result.get("isError")),
        len(output),
    )
    if result.get("isError"):
        return f"MCP tool error ({binding.server.name}/{binding.tool_name}): {output}"
    return output or f"MCP tool {binding.tool_name} completed successfully."
