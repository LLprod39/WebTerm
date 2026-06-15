from __future__ import annotations

import os
import re
from dataclasses import dataclass

from django.conf import settings

from studio.models import MCPServerPool


@dataclass(frozen=True)
class MCPStdioPolicyResult:
    allowed: bool
    error: str = ""


def _setting_list(name: str, default: tuple[str, ...]) -> tuple[str, ...]:
    raw = getattr(settings, name, os.getenv(name, ",".join(default)))
    if isinstance(raw, str):
        items = re.split(r"[,;\s]+", raw)
    else:
        items = list(raw or [])
    return tuple(str(item).strip().lower() for item in items if str(item).strip())


def _setting_bool(name: str, default: bool) -> bool:
    raw = getattr(settings, name, os.getenv(name, default))
    if isinstance(raw, bool):
        return raw
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def _command_name(command: str) -> str:
    name = re.split(r"[\\/]+", str(command or "").strip())[-1].lower()
    if name.endswith(".exe"):
        name = name[:-4]
    return name


def validate_stdio_mcp_policy(command: str, *, user=None, action: str = "run") -> MCPStdioPolicyResult:
    if not _setting_bool("STUDIO_MCP_STDIO_ENABLED", bool(getattr(settings, "DEBUG", False))):
        return MCPStdioPolicyResult(
            False,
            "Stdio MCP servers are disabled on this deployment.",
        )
    if user is not None and _setting_bool("STUDIO_MCP_STDIO_ADMIN_ONLY", True):
        if not bool(getattr(user, "is_staff", False)):
            return MCPStdioPolicyResult(
                False,
                f"Only admins can {action} stdio MCP servers.",
            )
    command_name = _command_name(command)
    if not command_name:
        return MCPStdioPolicyResult(False, "Stdio MCP command is required.")
    allowed_commands = _setting_list("STUDIO_MCP_STDIO_ALLOWED_COMMANDS", ("npx", "node", "python", "python3"))
    if allowed_commands and command_name not in allowed_commands:
        return MCPStdioPolicyResult(
            False,
            f"Stdio MCP command '{command_name}' is not allowed.",
        )
    return MCPStdioPolicyResult(True)


def validate_mcp_runtime_policy(mcp: MCPServerPool, *, user=None, action: str = "run") -> MCPStdioPolicyResult:
    if mcp.transport != MCPServerPool.TRANSPORT_STDIO:
        return MCPStdioPolicyResult(True)
    return validate_stdio_mcp_policy(mcp.command, user=user, action=action)
