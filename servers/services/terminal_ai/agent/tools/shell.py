"""
Shell execution tool for the Terminal Agent.

Runs a single shell command on the remote server via a non-PTY asyncssh
channel (same transport as the ``exec_mode=direct`` path of the legacy
executor). PTY commands are intentionally excluded from the agent loop —
the agent should break interactive tasks down into non-interactive
equivalents (``cat`` instead of ``less``, ``sed -i`` instead of ``vim``).

Safety
------
- the shared fail-closed execution gate auto-runs only classified read-only
  commands and pauses every other command for one-command operator approval.
- :func:`servers.services.terminal_ai.server_ai_policy.is_server_ai_read_only`
  short-circuits the tool on read-only servers (2.11) unless the command
  is itself read-only.
"""

from __future__ import annotations

import asyncio
import logging

from asgiref.sync import sync_to_async
from pydantic import BaseModel, ConfigDict, Field

from app.agent_kernel.permissions.shell_policy import is_read_only_command
from app.command_execution_gate import evaluate_command_execution_gate
from app.sudo_policy import command_uses_sudo, evaluate_sudo_command, prepare_sudo_command
from servers.services.terminal_ai.agent.schemas import ToolResult
from servers.services.terminal_ai.agent.tools.base import (
    ServerTarget,
    ToolContext,
    UserPromptOption,
    UserPromptRequest,
    tool_err,
    tool_ok,
)

logger = logging.getLogger(__name__)

# Hard limit on captured output — anything beyond is truncated before
# feeding back to the LLM.
_MAX_OUTPUT_CHARS = 8000

# Max timeout the agent can request for a single shell call.
_MAX_TIMEOUT_SEC = 300


class ShellArgs(BaseModel):
    """Arguments for the ``shell`` tool."""

    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    cmd: str = Field(min_length=1, max_length=4000)
    """Single shell command line (no trailing newline)."""

    target: str = Field(default="", max_length=64)
    """Server handle (empty = primary session server). Use `list_targets`
    to see available names."""

    timeout: int = Field(default=30, ge=1, le=_MAX_TIMEOUT_SEC)
    """Per-command timeout in seconds (bounded at 5 min)."""

    reason: str = Field(default="", max_length=300)
    """Short rationale logged to history — not executed."""


class ShellTool:
    """Execute a shell command on the remote server (non-PTY)."""

    name: str = "shell"
    description: str = (
        "Execute a single shell command on one of the authorised servers "
        "via a non-PTY SSH channel and return its stdout/stderr + exit "
        "code. Use for diagnostics, file queries, service control, etc. "
        "Do NOT use for interactive editors (vim/nano/less) — use "
        "`read_file` / `edit_file` instead. Set `target` to route to an "
        "authorised extra server (see `list_targets`); leave empty to "
        "hit the current session's server. Destructive commands are "
        "vetoed by the safety engine and return an error."
    )
    args_schema: type[BaseModel] = ShellArgs

    async def _approve_command_once(
        self,
        *,
        cmd: str,
        target: ServerTarget,
        reason: str,
        ctx: ToolContext,
    ) -> bool:
        if ctx.prompt_user is None:
            return False
        reply = await ctx.prompt_user(
            UserPromptRequest(
                question=(
                    "Nova запрашивает одноразовое разрешение на команду:\n"
                    f"`{cmd}`\n\nСервер: {target.display_name or target.name}. Причина: {reason}."
                ),
                timeout_seconds=300,
                options=[
                    UserPromptOption(
                        label="Разрешить один раз",
                        value="allow_once",
                        description="Разрешение действует только для этого вызова команды.",
                    ),
                    UserPromptOption(
                        label="Заблокировать",
                        value="block",
                        description="Команда не будет выполнена.",
                    ),
                ],
                allow_multiple=False,
                free_text_allowed=False,
            )
        )
        return str(reply or "").strip().lower() in {"allow_once", "allow", "yes", "y", "да", "разрешить"}

    async def _approve_sudo_once(self, *, cmd: str, target: ServerTarget, ctx: ToolContext) -> bool:
        if ctx.prompt_user is None:
            return False
        reply = await ctx.prompt_user(
            UserPromptRequest(
                question=(
                    "Nova требуется sudo для команды:\n"
                    f"`{cmd}`\n\n"
                    f"Сервер: {target.display_name or target.name}. Разрешить выполнение один раз?"
                ),
                timeout_seconds=300,
                options=[
                    UserPromptOption(
                        label="Разрешить один раз",
                        value="allow_once",
                        description="Backend выполнит команду с sudo без передачи пароля Nova.",
                    ),
                    UserPromptOption(
                        label="Заблокировать",
                        value="block",
                        description="Команда не будет выполнена.",
                    ),
                ],
                allow_multiple=False,
                free_text_allowed=False,
            )
        )
        return str(reply or "").strip().lower() in {"allow_once", "allow", "yes", "y", "да", "разрешить"}

    async def _resolve_sudo_password(self, *, target: ServerTarget, ctx: ToolContext) -> str:
        if target.sudo_auth_mode != "stored_password":
            return ""
        if not ctx.user_id:
            return ""
        from servers.secret_utils import get_server_sudo_secret
        from servers.services.terminal_agent_context import load_user_accessible_server

        server = await load_user_accessible_server(user_id=int(ctx.user_id), server_id=int(target.server_id))
        if server is None:
            return ""
        return await sync_to_async(get_server_sudo_secret, thread_sensitive=True)(server)

    async def run(self, args: ShellArgs, ctx: ToolContext) -> ToolResult:
        cmd = args.cmd.strip()
        if not cmd:
            return tool_err("empty command")

        # Multi-line guard: each shell call should be one statement.
        if "\n" in cmd:
            return tool_err("multi-line commands are not allowed; call `shell` once per line")

        # Target resolution (multi-server).
        target = ctx.resolve_target(args.target)
        if target is None:
            available = ", ".join(t.name for t in ctx.all_targets()) or "(none)"
            return tool_err(
                f"unknown target '{args.target}'; available: {available}",
                output=(
                    f"Target '{args.target}' is not authorised for this "
                    f"session. Available: {available}. Use `list_targets`."
                ),
            )

        gate = evaluate_command_execution_gate(cmd)

        # Read-only is an immutable target boundary, not an approval prompt.
        if target.read_only and not is_read_only_command(cmd):
            return tool_err(
                f"target '{target.name}' is in read-only mode",
                output=(
                    f"Server '{target.display_name or target.name}' only allows "
                    "commands from the built-in read-only allowlist."
                ),
            )

        if gate.requires_approval and not await self._approve_command_once(
            cmd=cmd,
            target=target,
            reason=gate.reason,
            ctx=ctx,
        ):
            return tool_err(
                f"command requires explicit operator approval: {cmd[:120]}",
                output="Команда не выполнена: оператор не дал одноразовое разрешение.",
            )

        sudo_notes: tuple[str, ...] = ()
        sudo_input_text: str | None = None
        sudo_policy = str(ctx.sudo_policy or "disabled")
        if command_uses_sudo(cmd):
            sudo_decision = evaluate_sudo_command(cmd, sudo_policy)
            effective_sudo_policy = sudo_policy
            if not sudo_decision.allowed:
                if sudo_decision.matched_patterns == ("sudo_requires_operator_approval",):
                    approved = await self._approve_sudo_once(cmd=cmd, target=target, ctx=ctx)
                    if not approved:
                        return tool_err(
                            "sudo command blocked by operator policy",
                            output="Команда с sudo не выполнена: оператор не дал разрешение.",
                        )
                    effective_sudo_policy = "approved"
                else:
                    return tool_err(
                        sudo_decision.reason or "sudo command blocked",
                        output=sudo_decision.reason or "Команда с sudo заблокирована настройками Nova.",
                    )
            try:
                prepared_sudo = prepare_sudo_command(
                    cmd,
                    effective_sudo_policy,
                    sudo_auth_mode=target.sudo_auth_mode,
                    sudo_password=await self._resolve_sudo_password(target=target, ctx=ctx),
                )
            except ValueError as exc:
                return tool_err(str(exc))
            cmd = prepared_sudo.command
            sudo_notes = prepared_sudo.notes
            sudo_input_text = prepared_sudo.input_text

        # Dry-run short-circuit: no SSH call at all.
        if ctx.dry_run:
            return tool_ok(
                f"[DRY-RUN on {target.name}] Would execute: {cmd}\nExit: 0",
                data={
                    "exit_code": 0,
                    "dry_run": True,
                    "cmd": cmd,
                    "target": target.name,
                },
            )

        conn = await ctx.ensure_connection(target)
        if conn is None:
            return tool_err(
                f"SSH connection to target '{target.name}' unavailable",
                fatal=target.is_primary,
            )

        timeout = min(max(int(args.timeout or 30), 1), _MAX_TIMEOUT_SEC)

        run_kwargs: dict[str, object] = {"check": False}
        if sudo_input_text is not None:
            run_kwargs["input"] = sudo_input_text

        try:
            result = await asyncio.wait_for(
                conn.run(cmd, **run_kwargs),
                timeout=timeout,
            )
        except TimeoutError:
            return tool_err(
                f"command timed out after {timeout}s on {target.name}",
                output=f"TIMEOUT after {timeout}s on {target.name}: {cmd[:200]}",
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("agent shell tool failed on %s: %s", target.name, exc)
            return tool_err(f"{type(exc).__name__}: {exc}")

        stdout = str(getattr(result, "stdout", "") or "")
        stderr = str(getattr(result, "stderr", "") or "")
        exit_code = getattr(result, "exit_status", None)
        exit_code = int(exit_code) if exit_code is not None else 1

        combined = stdout + (("\n" + stderr) if stderr else "")
        if sudo_notes:
            combined = "\n".join(sudo_notes) + "\n" + combined
        # Tail-truncate: the last chunk is usually the most useful part
        # of long logs. Prepend a marker so the LLM knows output was cut.
        if len(combined) > _MAX_OUTPUT_CHARS:
            combined = (
                f"[... {len(combined) - _MAX_OUTPUT_CHARS} chars truncated ...]\n" + combined[-_MAX_OUTPUT_CHARS:]
            )

        output_payload = (f"Target: {target.name}\nExit: {exit_code}\n{combined}").strip()
        return tool_ok(
            output_payload,
            data={
                "exit_code": exit_code,
                "stdout_bytes": len(stdout),
                "stderr_bytes": len(stderr),
                "cmd": cmd,
                "target": target.name,
                "sudo_notes": list(sudo_notes),
            },
        )


__all__ = ["ShellTool", "ShellArgs"]
