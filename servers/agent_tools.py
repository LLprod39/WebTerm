"""
Tools available to full ReAct agents.

Each tool is a callable returning a dict with at least {success: bool, result: str}.
Tools are registered in AGENT_TOOLS and described for the LLM prompt.
"""

from __future__ import annotations

import asyncio
import json
import re
from typing import TYPE_CHECKING, Any

from app.tools.safety import is_dangerous_command

if TYPE_CHECKING:
    from servers.agent_sessions import AgentSessionManager


class ToolResult:
    __slots__ = ("success", "result", "data")

    def __init__(self, success: bool, result: str, data: dict | None = None):
        self.success = success
        self.result = result
        self.data = data or {}

    def to_dict(self) -> dict:
        d = {"success": self.success, "result": self.result}
        if self.data:
            d["data"] = self.data
        return d


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------

async def tool_ssh_execute(session: AgentSessionManager, *, server: str, command: str, **_kw) -> ToolResult:
    """Execute a shell command on the specified server."""
    sid = session.resolve_server(server)
    if sid is None:
        return ToolResult(False, f"Server '{server}' not found or not connected.")

    if is_dangerous_command(command):
        return ToolResult(False, f"Blocked: command is dangerous — {command}")

    forbidden = session.get_forbidden_patterns(sid)
    if _matches_forbidden(command, forbidden):
        return ToolResult(False, f"Blocked: command matches forbidden pattern — {command}")

    try:
        out = await session.execute(sid, command)
        return ToolResult(
            success=out["exit_code"] == 0,
            result=out["stdout"][:6000] + (f"\nSTDERR: {out['stderr'][:1000]}" if out.get("stderr") else ""),
            data={"exit_code": out["exit_code"], "duration_ms": out.get("duration_ms", 0)},
        )
    except asyncio.TimeoutError:
        return ToolResult(False, f"Command timed out after {session.command_timeout}s: {command}")
    except Exception as exc:
        return ToolResult(False, f"SSH error: {exc}")


async def tool_read_console(session: AgentSessionManager, *, server: str, lines: int = 80, **_kw) -> ToolResult:
    """Read the latest console output for a server."""
    sid = session.resolve_server(server)
    if sid is None:
        return ToolResult(False, f"Server '{server}' not found or not connected.")

    buf = session.read_output(sid)
    if not buf:
        return ToolResult(True, "(console is empty)")
    tail = "\n".join(buf.splitlines()[-lines:])
    return ToolResult(True, tail)


async def tool_send_ctrl_c(session: AgentSessionManager, *, server: str, **_kw) -> ToolResult:
    """Send Ctrl+C (SIGINT) to the running process on a server."""
    sid = session.resolve_server(server)
    if sid is None:
        return ToolResult(False, f"Server '{server}' not found or not connected.")
    try:
        await session.send_signal(sid, "ctrl_c")
        return ToolResult(True, "Ctrl+C sent.")
    except Exception as exc:
        return ToolResult(False, f"Failed to send Ctrl+C: {exc}")


async def tool_open_connection(session: AgentSessionManager, *, server: str, **_kw) -> ToolResult:
    """Open a new SSH connection to a server (by name or id)."""
    sid = session.resolve_server(server)
    if sid is not None and sid in session.connections:
        return ToolResult(True, f"Already connected to {server}.")

    srv_obj = session.find_server_object(server)
    if srv_obj is None:
        return ToolResult(False, f"Server '{server}' not found in agent scope.")

    if len(session.connections) >= session.max_connections:
        return ToolResult(False, f"Max connections ({session.max_connections}) reached. Close one first.")

    try:
        await session.open(srv_obj)
        return ToolResult(True, f"Connected to {srv_obj.name} ({srv_obj.host}).")
    except Exception as exc:
        return ToolResult(False, f"Connection failed: {exc}")


async def tool_close_connection(session: AgentSessionManager, *, server: str, **_kw) -> ToolResult:
    """Close an SSH connection."""
    sid = session.resolve_server(server)
    if sid is None:
        return ToolResult(False, f"Server '{server}' not found or not connected.")
    await session.close(sid)
    return ToolResult(True, f"Connection to '{server}' closed.")


async def tool_wait_for_output(
    session: AgentSessionManager, *, server: str, pattern: str, timeout: int = 30, **_kw,
) -> ToolResult:
    """Wait until a regex pattern appears in the server console output."""
    sid = session.resolve_server(server)
    if sid is None:
        return ToolResult(False, f"Server '{server}' not found or not connected.")

    try:
        matched = await session.wait_for_pattern(sid, pattern, timeout)
        return ToolResult(True, f"Pattern found: {matched[:500]}")
    except asyncio.TimeoutError:
        buf_tail = session.read_output(sid)[-500:]
        return ToolResult(False, f"Pattern '{pattern}' not found within {timeout}s. Last output:\n{buf_tail}")


async def tool_report(session: AgentSessionManager, *, text: str, **_kw) -> ToolResult:
    """Send an intermediate report to the user (visible in live monitor)."""
    if session.event_callback:
        await session.event_callback("agent_report", {"text": text, "interim": True})
    return ToolResult(True, "Report sent.")


async def tool_ask_user(session: AgentSessionManager, *, question: str, **_kw) -> ToolResult:
    """Ask the user a question and wait for a response (pauses the agent)."""
    if session.event_callback:
        await session.event_callback("agent_question", {"question": question})
    if session.user_reply_future is not None and not session.user_reply_future.done():
        session.user_reply_future.cancel()
    session.user_reply_future = asyncio.get_event_loop().create_future()
    try:
        answer = await asyncio.wait_for(session.user_reply_future, timeout=300)
        return ToolResult(True, f"User replied: {answer}")
    except asyncio.CancelledError:
        return ToolResult(False, "User input was interrupted.")
    except asyncio.TimeoutError:
        return ToolResult(False, "User did not reply within 5 minutes.")


async def tool_analyze_output(session: AgentSessionManager, *, text: str, question: str, **_kw) -> ToolResult:
    """Ask the LLM to analyze a specific piece of output."""
    from app.core.llm import LLMProvider

    prompt = f"Analyze the following output and answer the question.\n\nOutput:\n```\n{text[:4000]}\n```\n\nQuestion: {question}"
    provider = LLMProvider()
    chunks = []
    try:
        async for chunk in provider.stream_chat(prompt, model="auto"):
            chunks.append(chunk)
        return ToolResult(True, "".join(chunks))
    except Exception as exc:
        return ToolResult(False, f"LLM analysis failed: {exc}")


async def tool_list_skills(session: AgentSessionManager, **_kw) -> ToolResult:
    """List attached skills available to the current agent run."""
    skills = session.list_skills()
    if not skills:
        return ToolResult(True, '{"skills": []}')
    return ToolResult(True, json.dumps({"skills": skills}, ensure_ascii=False, indent=2))


async def tool_read_skill(session: AgentSessionManager, *, skill: str, **_kw) -> ToolResult:
    """Read the full content of an attached skill by slug or display name."""
    item = session.get_skill(skill)
    if item is None:
        return ToolResult(False, f"Skill '{skill}' is not attached to this agent.")

    content = str(item.get("content") or "").strip()
    if not content:
        return ToolResult(False, f"Skill '{skill}' is empty.")

    header = {
        "slug": item.get("slug", ""),
        "name": item.get("name", ""),
        "description": item.get("description", ""),
        "tags": list(item.get("tags") or []),
        "service": item.get("service", ""),
        "category": item.get("category", ""),
        "safety_level": item.get("safety_level", ""),
        "ui_hint": item.get("ui_hint", ""),
        "guardrail_summary": list(item.get("guardrail_summary") or []),
        "recommended_tools": list(item.get("recommended_tools") or []),
        "runtime_enforced": bool(item.get("runtime_policy")),
        "path": item.get("path", ""),
    }
    body = json.dumps(header, ensure_ascii=False, indent=2)
    return ToolResult(True, f"{body}\n\n{content[:20000]}")


# ---------------------------------------------------------------------------
# Tool registry
# ---------------------------------------------------------------------------

AGENT_TOOLS: dict[str, dict[str, Any]] = {
    "ssh_execute": {
        "fn": tool_ssh_execute,
        "description": "Execute a shell command on a server and return stdout/stderr/exit_code.",
        "params": {
            "server": {"type": "string", "required": True, "description": "Server name or id"},
            "command": {"type": "string", "required": True, "description": "Shell command to execute"},
        },
    },
    "read_console": {
        "fn": tool_read_console,
        "description": "Read the latest console output (last N lines) from a server.",
        "params": {
            "server": {"type": "string", "required": True, "description": "Server name or id"},
            "lines": {"type": "integer", "required": False, "description": "Number of lines (default 80)"},
        },
    },
    "send_ctrl_c": {
        "fn": tool_send_ctrl_c,
        "description": "Send Ctrl+C to interrupt the current running command on a server.",
        "params": {
            "server": {"type": "string", "required": True, "description": "Server name or id"},
        },
    },
    "open_connection": {
        "fn": tool_open_connection,
        "description": "Open a new SSH connection to a server (if not already connected).",
        "params": {
            "server": {"type": "string", "required": True, "description": "Server name or id"},
        },
    },
    "close_connection": {
        "fn": tool_close_connection,
        "description": "Close an existing SSH connection to free resources.",
        "params": {
            "server": {"type": "string", "required": True, "description": "Server name or id"},
        },
    },
    "wait_for_output": {
        "fn": tool_wait_for_output,
        "description": "Wait for a regex pattern to appear in the server console output.",
        "params": {
            "server": {"type": "string", "required": True, "description": "Server name or id"},
            "pattern": {"type": "string", "required": True, "description": "Regex pattern to wait for"},
            "timeout": {"type": "integer", "required": False, "description": "Timeout in seconds (default 30)"},
        },
    },
    "report": {
        "fn": tool_report,
        "description": "Send an intermediate progress report to the user.",
        "params": {
            "text": {"type": "string", "required": True, "description": "Report text (Markdown)"},
        },
    },
    "ask_user": {
        "fn": tool_ask_user,
        "description": "Ask the user a question and wait for their reply. Use for ambiguous or dangerous situations.",
        "params": {
            "question": {"type": "string", "required": True, "description": "Question to ask"},
        },
    },
    "analyze_output": {
        "fn": tool_analyze_output,
        "description": "Ask the AI to analyze a piece of output and answer a question about it.",
        "params": {
            "text": {"type": "string", "required": True, "description": "Text to analyze"},
            "question": {"type": "string", "required": True, "description": "Question about the text"},
        },
    },
    "list_skills": {
        "fn": tool_list_skills,
        "description": "List the attached skills available to this agent. Use before read_skill if you need service-specific guidance.",
        "params": {},
    },
    "read_skill": {
        "fn": tool_read_skill,
        "description": "Read the full content of an attached skill by slug or name.",
        "params": {
            "skill": {"type": "string", "required": True, "description": "Skill slug or display name"},
        },
    },
}


def get_tools_description(enabled_tools: list[str] | None = None) -> str:
    """Build a human-readable tool description for the LLM system prompt."""
    lines = []
    for name, meta in AGENT_TOOLS.items():
        if enabled_tools is not None and name not in enabled_tools:
            continue
        params_parts = []
        for pname, pinfo in meta["params"].items():
            req = " (required)" if pinfo.get("required") else ""
            params_parts.append(f"  - {pname}: {pinfo['type']}{req} — {pinfo['description']}")
        params_str = "\n".join(params_parts) if params_parts else "  (no parameters)"
        lines.append(f"### {name}\n{meta['description']}\nParameters:\n{params_str}")
    return "\n\n".join(lines)


def get_enabled_tools(tools_config: dict) -> list[str]:
    """Return list of enabled tool names based on agent config."""
    if not tools_config:
        return list(AGENT_TOOLS.keys())
    return [name for name in AGENT_TOOLS if tools_config.get(name, False)]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _matches_forbidden(cmd: str, patterns: list[str]) -> bool:
    cmd_l = cmd.lower().strip()
    for pat in patterns:
        pat_s = pat.strip()
        if not pat_s:
            continue
        if pat_s.startswith("re:"):
            try:
                if re.search(pat_s[3:], cmd_l, re.IGNORECASE):
                    return True
            except re.error:
                pass
        elif pat_s.lower() in cmd_l:
            return True
    return False
