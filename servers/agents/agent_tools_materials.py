"""Agent tools for attached skills and operator materials (F-08a split of agent_tools)."""

from __future__ import annotations

import contextlib
import json
import re
from typing import TYPE_CHECKING

from servers.agents.agent_tools_base import ToolResult

if TYPE_CHECKING:
    from servers.agents.agent_sessions import AgentSessionManager


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
        return ToolResult(
            True, json.dumps({"materials": [], "hint": "No operator materials attached."}, ensure_ascii=False)
        )
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
        write_parts.append(f'B64="${{B64}}{chunk}"')
    write_b64 = "\n".join(write_parts)

    args_str = str(args or "").strip()
    # Only allow simple shell-safe args
    if args_str and not re.fullmatch(r"[A-Za-z0-9_./=\s\-:,@+]+", args_str):
        return ToolResult(False, "args contains unsupported characters; use letters, digits, ./_-=:@+ and spaces.")
    args_quoted = " ".join(shlex.quote(part) for part in args_str.split()) if args_str else ""

    dry = dry_run.strip().lower() in {"1", "true", "yes", "on"} if isinstance(dry_run, str) else bool(dry_run)
    if dry:
        run_block = (
            "echo '=== DRY RUN: head ==='\n"
            'head -n 60 "$SCRIPT"\n'
            "echo '=== DRY RUN: bash -n ==='\n"
            "if command -v bash >/dev/null 2>&1; then bash -n \"$SCRIPT\"; else echo 'bash not found, skip -n'; fi\n"
            "EC=$?\n"
        )
    else:
        run_block = f'timeout {timeout_sec} bash "$SCRIPT" {args_quoted}\nEC=$?\n'

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
    except TimeoutError:
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
