"""
Tools available to full ReAct agents.

Each tool is a callable returning a dict with at least {success: bool, result: str}.
Tools are registered in AGENT_TOOLS and described for the LLM prompt.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import re
from typing import TYPE_CHECKING, Any

from app.plugins.agent_tools import plugin_agent_tool_specs
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


async def tool_list_materials(session: AgentSessionManager, **_kw) -> ToolResult:
    """List operator-provided materials available to this agent run."""
    materials = session.list_materials()
    if not materials:
        return ToolResult(True, json.dumps({"materials": [], "hint": "No operator materials attached."}, ensure_ascii=False))
    return ToolResult(
        True,
        json.dumps(
            {
                "materials": materials,
                "hint": (
                    "Use read_material for full body; run_script_material for kind=script; "
                    "update_material_task for task_list progress."
                ),
            },
            ensure_ascii=False,
            indent=2,
        ),
    )


async def tool_read_material(session: AgentSessionManager, *, material: str, **_kw) -> ToolResult:
    """Read full content of a material by id or name."""
    item = session.get_material(material)
    if item is None:
        catalog = session.list_materials()
        ids = ", ".join(f"{m['id']}({m['kind']})" for m in catalog) or "(none)"
        return ToolResult(False, f"Material '{material}' not found. Available: {ids}")

    payload = {
        "id": item.get("id"),
        "kind": item.get("kind"),
        "name": item.get("name"),
        "run_hint": item.get("run_hint") or "",
        "source_name": item.get("source_name") or "",
    }
    if item.get("kind") == "task_list" and item.get("tasks"):
        payload["tasks"] = item.get("tasks")
    body = json.dumps(payload, ensure_ascii=False, indent=2)
    content = str(item.get("content") or "")
    return ToolResult(True, f"{body}\n\n{content[:20000]}")


async def tool_update_material_task(
    session: AgentSessionManager,
    *,
    material: str,
    task_index: int,
    status: str,
    evidence: str = "",
    **_kw,
) -> ToolResult:
    """Update a task_list item status with optional evidence."""
    try:
        index = int(task_index)
    except (TypeError, ValueError):
        return ToolResult(False, "task_index must be an integer (0-based).")
    updated = session.update_material_task(material, index, status=status, evidence=evidence)
    if updated is None:
        item = session.get_material(material)
        if item is None:
            return ToolResult(False, f"Material '{material}' not found.")
        if item.get("kind") != "task_list":
            return ToolResult(False, f"Material '{material}' is not a task_list.")
        return ToolResult(False, f"Invalid task_index={task_index} or status={status!r}.")
    tasks = list(updated.get("tasks") or [])
    open_count = sum(1 for t in tasks if str(t.get("status") or "pending") not in {"done", "skipped"})
    return ToolResult(
        True,
        json.dumps(
            {
                "material_id": updated.get("id"),
                "task_index": index,
                "task": tasks[index] if 0 <= index < len(tasks) else None,
                "tasks_open": open_count,
                "tasks_total": len(tasks),
            },
            ensure_ascii=False,
            indent=2,
        ),
    )


async def tool_run_script_material(
    session: AgentSessionManager,
    *,
    material: str,
    server: str,
    args: str = "",
    dry_run: bool = False,
    timeout: int = 300,
    **_kw,
) -> ToolResult:
    """Stage and run an operator-provided script material on a server (do not rewrite it)."""
    import base64
    import shlex

    item = session.get_material(material)
    if item is None:
        catalog = [m for m in session.list_materials() if m.get("kind") == "script"]
        ids = ", ".join(f"{m['id']}:{m['name']}" for m in catalog) or "(no scripts)"
        return ToolResult(False, f"Script material '{material}' not found. Scripts: {ids}")
    if item.get("kind") != "script":
        return ToolResult(False, f"Material '{item.get('id')}' kind is {item.get('kind')}, not script.")

    content = str(item.get("content") or "")
    if not content.strip():
        return ToolResult(False, f"Script material '{item.get('id')}' is empty.")

    # Block obvious destruction before staging
    dangerous_hits = [
        token
        for token in (
            "rm -rf /",
            "mkfs",
            "dd if=",
            ":(){",
            "shutdown",
            "reboot",
            "userdel",
            "passwd ",
        )
        if token in content
    ]
    if dangerous_hits and not dry_run:
        return ToolResult(
            False,
            "Blocked: script content matches high-risk patterns "
            f"({', '.join(dangerous_hits)}). Use dry_run=true to inspect, or ask_user.",
        )

    sid = session.resolve_server(server)
    if sid is None:
        return ToolResult(False, f"Server '{server}' not found or not connected. Use open_connection first.")

    try:
        timeout_sec = max(15, min(int(timeout or 300), 900))
    except (TypeError, ValueError):
        timeout_sec = 300

    b64 = base64.b64encode(content.encode("utf-8")).decode("ascii")
    # Chunk base64 into shell-safe lines for very large scripts
    chunk_size = 4000
    chunks = [b64[i : i + chunk_size] for i in range(0, len(b64), chunk_size)]
    write_parts = ["B64=''"]
    for chunk in chunks:
        write_parts.append(f"B64=\"${{B64}}{chunk}\"")
    write_b64 = "\n".join(write_parts)

    args_str = str(args or "").strip()
    # Only allow simple shell-safe args
    if args_str and not re.fullmatch(r"[A-Za-z0-9_./=\s\-:,@+]+", args_str):
        return ToolResult(False, "args contains unsupported characters; use letters, digits, ./_-=:@+ and spaces.")
    args_quoted = " ".join(shlex.quote(part) for part in args_str.split()) if args_str else ""

    if isinstance(dry_run, str):
        dry = dry_run.strip().lower() in {"1", "true", "yes", "on"}
    else:
        dry = bool(dry_run)
    if dry:
        run_block = (
            "echo '=== DRY RUN: head ==='\n"
            "head -n 60 \"$SCRIPT\"\n"
            "echo '=== DRY RUN: bash -n ==='\n"
            "if command -v bash >/dev/null 2>&1; then bash -n \"$SCRIPT\"; else echo 'bash not found, skip -n'; fi\n"
            "EC=$?\n"
        )
    else:
        run_block = (
            f"timeout {timeout_sec} bash \"$SCRIPT\" {args_quoted}\n"
            "EC=$?\n"
        )

    remote = f"""set -e
WORKDIR=$(mktemp -d /tmp/webterm-mat.XXXXXX)
SCRIPT="$WORKDIR/operator_script.sh"
{write_b64}
printf '%s' "$B64" | base64 -d > "$SCRIPT"
chmod 700 "$SCRIPT"
set +e
{run_block}
set -e
echo "WEBTERM_SCRIPT_EXIT=$EC"
echo "WEBTERM_SCRIPT_PATH=$SCRIPT"
echo '=== STDOUT/ERR captured above ==='
rm -rf "$WORKDIR" 2>/dev/null || true
exit 0
"""
    try:
        out = await session.execute(sid, f"bash -lc {shlex.quote(remote)}")
    except asyncio.TimeoutError:
        return ToolResult(False, f"Script material timed out (server timeout). material={item.get('id')}")
    except Exception as exc:
        return ToolResult(False, f"SSH error while running script material: {exc}")

    stdout = str(out.get("stdout") or "")
    stderr = str(out.get("stderr") or "")
    exit_code = out.get("exit_code")
    script_exit = None
    for line in stdout.splitlines():
        if line.startswith("WEBTERM_SCRIPT_EXIT="):
            with contextlib.suppress(ValueError):
                script_exit = int(line.split("=", 1)[1].strip())
    combined = stdout
    if stderr:
        combined = f"{stdout}\nSTDERR:\n{stderr}" if stdout else f"STDERR:\n{stderr}"
    success = (script_exit == 0) if script_exit is not None else (exit_code == 0)
    mode = "dry_run" if dry else "execute"
    header = (
        f"run_script_material mode={mode} id={item.get('id')} name={item.get('name')!r} "
        f"server={server} script_exit={script_exit if script_exit is not None else 'unknown'} "
        f"ssh_exit={exit_code}\n"
        f"hint={item.get('run_hint') or ''}\n"
        "Next: verify host side-effects (services/logs/ports); do not rewrite this script — re-run or fix config."
    )
    return ToolResult(
        success=success,
        result=f"{header}\n\n{combined[:8000]}",
        data={
            "material_id": item.get("id"),
            "script_exit": script_exit,
            "exit_code": exit_code,
            "dry_run": dry,
            "duration_ms": out.get("duration_ms", 0),
        },
    )


# ---------------------------------------------------------------------------
# Tool registry
# ---------------------------------------------------------------------------

AGENT_TOOLS: dict[str, dict[str, Any]] = {
    "ssh_execute": {
        "fn": tool_ssh_execute,
        "description": "Execute a shell command on a server and return stdout/stderr/exit_code.",
        "tool_spec": {
            "category": "ssh",
            "risk": "exec",
            "requires_verification": True,
            "output_compactor": "tail",
        },
        "params": {
            "server": {"type": "string", "required": True, "description": "Server name or id"},
            "command": {"type": "string", "required": True, "description": "Shell command to execute"},
        },
    },
    "read_console": {
        "fn": tool_read_console,
        "description": "Read the latest console output (last N lines) from a server.",
        "tool_spec": {
            "category": "monitoring",
            "risk": "read",
            "output_compactor": "tail",
        },
        "params": {
            "server": {"type": "string", "required": True, "description": "Server name or id"},
            "lines": {"type": "integer", "required": False, "description": "Number of lines (default 80)"},
        },
    },
    "send_ctrl_c": {
        "fn": tool_send_ctrl_c,
        "description": "Send Ctrl+C to interrupt the current running command on a server.",
        "tool_spec": {
            "category": "service",
            "risk": "exec",
            "output_compactor": "tail",
        },
        "params": {
            "server": {"type": "string", "required": True, "description": "Server name or id"},
        },
    },
    "open_connection": {
        "fn": tool_open_connection,
        "description": "Open a new SSH connection to a server (if not already connected).",
        "tool_spec": {
            "category": "service",
            "risk": "exec",
            "output_compactor": "tail",
        },
        "params": {
            "server": {"type": "string", "required": True, "description": "Server name or id"},
        },
    },
    "close_connection": {
        "fn": tool_close_connection,
        "description": "Close an existing SSH connection to free resources.",
        "tool_spec": {
            "category": "service",
            "risk": "exec",
            "output_compactor": "tail",
        },
        "params": {
            "server": {"type": "string", "required": True, "description": "Server name or id"},
        },
    },
    "wait_for_output": {
        "fn": tool_wait_for_output,
        "description": "Wait for a regex pattern to appear in the server console output.",
        "tool_spec": {
            "category": "monitoring",
            "risk": "read",
            "output_compactor": "tail",
        },
        "params": {
            "server": {"type": "string", "required": True, "description": "Server name or id"},
            "pattern": {"type": "string", "required": True, "description": "Regex pattern to wait for"},
            "timeout": {"type": "integer", "required": False, "description": "Timeout in seconds (default 30)"},
        },
    },
    "report": {
        "fn": tool_report,
        "description": "Send an intermediate progress report to the user.",
        "tool_spec": {
            "category": "general",
            "risk": "read",
            "output_compactor": "tail",
        },
        "params": {
            "text": {"type": "string", "required": True, "description": "Report text (Markdown)"},
        },
    },
    "ask_user": {
        "fn": tool_ask_user,
        "description": "Ask the user a question and wait for their reply. Use for ambiguous or dangerous situations.",
        "tool_spec": {
            "category": "general",
            "risk": "read",
            "output_compactor": "tail",
        },
        "params": {
            "question": {"type": "string", "required": True, "description": "Question to ask"},
        },
    },
    "analyze_output": {
        "fn": tool_analyze_output,
        "description": "Ask the AI to analyze a piece of output and answer a question about it.",
        "tool_spec": {
            "category": "general",
            "risk": "read",
            "output_compactor": "tail",
        },
        "params": {
            "text": {"type": "string", "required": True, "description": "Text to analyze"},
            "question": {"type": "string", "required": True, "description": "Question about the text"},
        },
    },
    "list_skills": {
        "fn": tool_list_skills,
        "description": "List the attached skills available to this agent. Use before read_skill if you need service-specific guidance.",
        "tool_spec": {
            "category": "general",
            "risk": "read",
            "output_compactor": "tail",
        },
        "params": {},
    },
    "read_skill": {
        "fn": tool_read_skill,
        "description": "Read the full content of an attached skill by slug or name.",
        "tool_spec": {
            "category": "general",
            "risk": "read",
            "output_compactor": "tail",
        },
        "params": {
            "skill": {"type": "string", "required": True, "description": "Skill slug or display name"},
        },
    },
    "list_materials": {
        "fn": tool_list_materials,
        "description": (
            "List operator-provided materials (documents, task lists, scripts) with ids. "
            "Call early when materials may help; prefer operator scripts over writing your own."
        ),
        "tool_spec": {
            "category": "general",
            "risk": "read",
            "output_compactor": "tail",
        },
        "params": {},
    },
    "read_material": {
        "fn": tool_read_material,
        "description": "Read full content of a material by id or name (from list_materials).",
        "tool_spec": {
            "category": "general",
            "risk": "read",
            "output_compactor": "tail",
        },
        "params": {
            "material": {"type": "string", "required": True, "description": "Material id (e.g. m1) or name"},
        },
    },
    "run_script_material": {
        "fn": tool_run_script_material,
        "description": (
            "Stage and execute an operator-provided script material on a server. "
            "Do NOT rewrite the script; use this tool. Optional dry_run for preview/syntax check. "
            "After run, verify host side-effects."
        ),
        "tool_spec": {
            "category": "ssh",
            "risk": "exec",
            "requires_verification": True,
            "mutates_state": True,
            "output_compactor": "tail",
        },
        "params": {
            "material": {"type": "string", "required": True, "description": "Script material id or name"},
            "server": {"type": "string", "required": True, "description": "Server name or id"},
            "args": {"type": "string", "required": False, "description": "Optional CLI args passed to the script"},
            "dry_run": {"type": "boolean", "required": False, "description": "If true, preview + bash -n only"},
            "timeout": {"type": "integer", "required": False, "description": "Seconds (default 300, max 900)"},
        },
    },
    "update_material_task": {
        "fn": tool_update_material_task,
        "description": (
            "Update a task_list material item status with evidence "
            "(pending|in_progress|done|skipped|blocked)."
        ),
        "tool_spec": {
            "category": "general",
            "risk": "read",
            "output_compactor": "tail",
        },
        "params": {
            "material": {"type": "string", "required": True, "description": "task_list material id or name"},
            "task_index": {"type": "integer", "required": True, "description": "0-based task index"},
            "status": {
                "type": "string",
                "required": True,
                "description": "pending|in_progress|done|skipped|blocked",
            },
            "evidence": {"type": "string", "required": False, "description": "Short proof of completion/block"},
        },
    },
}


def get_all_agent_tools() -> dict[str, dict[str, Any]]:
    return {**AGENT_TOOLS, **plugin_agent_tool_specs()}


def get_tools_description(enabled_tools: list[str] | None = None) -> str:
    """Build a human-readable tool description for the LLM system prompt."""
    lines = []
    for name, meta in get_all_agent_tools().items():
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
    all_tools = get_all_agent_tools()
    if not tools_config:
        return list(all_tools.keys())
    return [name for name in all_tools if tools_config.get(name, False)]


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
