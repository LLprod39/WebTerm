"""
Meta tools for the Terminal Agent — control the loop itself.

These tools don't touch the remote server; they interact with the user,
update the shared todo list, or signal completion.

Included:
  * ``ask_user``    — pause and wait for a text reply
  * ``todo_write``  — replace/update the visible todo checklist
  * ``list_targets``— show which servers are authorised this session
  * ``remember``    — pin a durable fact to server memory
  * ``done``        — terminate the loop with a final user-facing message
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from servers.services.terminal_ai.agent.schemas import Todo, ToolResult
from servers.services.terminal_ai.agent.tools.base import (
    ToolContext,
    UserPromptOption,
    UserPromptRequest,
    tool_err,
    tool_ok,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# ask_user
# ---------------------------------------------------------------------------


class AskUserOption(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    label: str = Field(min_length=1, max_length=120)
    value: str = Field(min_length=1, max_length=240)
    description: str = Field(default="", max_length=240)


class AskUserArgs(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    question: str = Field(min_length=1, max_length=2000)
    timeout_seconds: int = Field(default=300, ge=5, le=1800)
    options: list[AskUserOption] = Field(default_factory=list, max_length=8)
    allow_multiple: bool = False
    free_text_allowed: bool = True
    placeholder: str = Field(default="", max_length=160)


class AskUserTool:
    """Pause the agent loop and request input from the human operator."""

    name: str = "ask_user"
    description: str = (
        "Pause the agent and ask the user a clarifying question. Use "
        "when you're stuck, when a destructive action needs approval, "
        "or when critical info is missing (credentials, hostnames, "
        "branch names). When the answer space is small, provide short "
        "Russian answer choices via `options` so the UI can render "
        "clickable selections. The user's reply is returned as the tool output."
    )
    args_schema: type[BaseModel] = AskUserArgs

    async def run(self, args: AskUserArgs, ctx: ToolContext) -> ToolResult:
        if ctx.prompt_user is None:
            return tool_err(
                "prompt_user not wired; cannot ask user in this context",
                fatal=True,
            )
        try:
            reply = await ctx.prompt_user(
                UserPromptRequest(
                    question=args.question,
                    timeout_seconds=float(args.timeout_seconds),
                    options=[
                        UserPromptOption(
                            label=option.label,
                            value=option.value,
                            description=option.description,
                        )
                        for option in args.options
                    ],
                    allow_multiple=bool(args.allow_multiple),
                    free_text_allowed=bool(args.free_text_allowed),
                    placeholder=args.placeholder,
                )
            )
        except Exception as exc:
            return tool_err(f"prompt_user failed: {exc}")

        if reply is None:
            return tool_err(
                "user did not reply in time (timeout)",
                output="User did not reply in time — consider a safer default.",
            )
        return tool_ok(
            f"User reply: {reply}",
            data={"reply": reply},
        )


# ---------------------------------------------------------------------------
# todo_write
# ---------------------------------------------------------------------------


class TodoWriteArgs(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    todos: list[Todo] = Field(default_factory=list, max_length=30)


class TodoWriteTool:
    """Replace the visible todo checklist so the user sees current plan."""

    name: str = "todo_write"
    description: str = (
        "Update the live todo checklist shown to the user. Pass the "
        "FULL new list — it REPLACES the old one. Each item has "
        "`id`, `content`, `status` (pending | in_progress | completed "
        "| cancelled). Keep ONE item `in_progress` at a time; mark it "
        "`completed` before moving to the next. Use this tool liberally "
        "to keep the user oriented on long tasks."
    )
    args_schema: type[BaseModel] = TodoWriteArgs

    async def run(self, args: TodoWriteArgs, ctx: ToolContext) -> ToolResult:
        new = [t.model_dump() for t in args.todos]
        ctx.todos[:] = new  # mutate in place so the loop picks it up

        if ctx.emit is not None:
            try:
                await ctx.emit({"type": "agent_todo_update", "todos": new})
            except Exception as exc:  # noqa: BLE001
                logger.debug("todo_write emit failed: %s", exc)

        in_progress = sum(1 for t in new if t["status"] == "in_progress")
        completed = sum(1 for t in new if t["status"] == "completed")
        return tool_ok(
            f"Todo updated: {len(new)} item(s), {in_progress} in progress, "
            f"{completed} done.",
            data={"todos": new},
        )


# ---------------------------------------------------------------------------
# list_targets
# ---------------------------------------------------------------------------


class ListTargetsArgs(BaseModel):
    model_config = ConfigDict(extra="ignore")


class ListTargetsTool:
    """Enumerate which servers the agent may touch this session."""

    name: str = "list_targets"
    description: str = (
        "List all servers authorised for this session: the primary server "
        "(the one the user opened the terminal on) plus any extras the "
        "user granted via session settings. Each entry gives a short "
        "`name` handle to pass as the `target` arg of other tools. If a "
        "required server is missing, call `ask_user` to request access."
    )
    args_schema: type[BaseModel] = ListTargetsArgs

    async def run(self, args: ListTargetsArgs, ctx: ToolContext) -> ToolResult:  # noqa: ARG002
        rows: list[dict[str, Any]] = []
        for t in ctx.all_targets():
            rows.append(
                {
                    "name": t.name,
                    "server_id": t.server_id,
                    "display_name": t.display_name,
                    "host": t.host,
                    "is_primary": t.is_primary,
                    "read_only": t.read_only,
                    "description": t.description,
                }
            )

        lines = [
            f"- {'PRIMARY' if r['is_primary'] else 'extra   '} "
            f"{r['name']!r} → {r['display_name'] or r['host']} "
            f"(id={r['server_id']}"
            + (", read-only" if r["read_only"] else "")
            + ")"
            for r in rows
        ]
        body = "\n".join(lines) if lines else "(no targets configured)"
        return tool_ok(
            f"Authorised targets this session ({len(rows)}):\n{body}",
            data={"targets": rows},
        )


# ---------------------------------------------------------------------------
# remember
# ---------------------------------------------------------------------------


class RememberArgs(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    fact: str = Field(min_length=3, max_length=800)
    """Durable context about the primary server — e.g. 'uses nginx on
    port 8443, not 443', 'cron runs backup.sh at 03:00 UTC'."""

    kind: str = Field(default="note", max_length=32)
    """Short category tag: ``note`` / ``warning`` / ``credential-hint``."""


class RememberTool:
    """Pin a durable fact to the primary server's layered memory."""

    name: str = "remember"
    description: str = (
        "Pin a durable fact about the primary server to its persistent "
        "memory. The fact becomes part of the agent context on future "
        "sessions for this server. Use sparingly — only for things "
        "that generalise beyond the current task (layouts, conventions, "
        "gotchas). Do NOT use for ephemeral state."
    )
    args_schema: type[BaseModel] = RememberArgs

    async def run(self, args: RememberArgs, ctx: ToolContext) -> ToolResult:
        if ctx.primary is None or not ctx.primary.server_id:
            return tool_err("no primary server in context")
        if ctx.user_id is None:
            return tool_err("user_id missing")

        try:
            from asgiref.sync import sync_to_async

            from servers.services.terminal_ai.memory import save_server_profile_sync

            await sync_to_async(save_server_profile_sync)(
                server_id=ctx.primary.server_id,
                user_id=ctx.user_id,
                summary="",
                facts=[args.fact.strip()],
                issues=[],
            )
        except Exception as exc:  # noqa: BLE001 — memory write best-effort
            logger.warning("remember tool failed: %s", exc)
            return tool_err(f"memory write failed: {exc}")

        return tool_ok(
            f"Remembered for server {ctx.primary.display_name or ctx.primary.name}: "
            f"{args.fact[:200]}",
            data={
                "fact": args.fact,
                "kind": args.kind,
                "server_id": ctx.primary.server_id,
            },
        )


# ---------------------------------------------------------------------------
# done (pseudo-tool — the loop intercepts this name and terminates)
# ---------------------------------------------------------------------------


class DoneArgs(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    final_text: str = Field(default="", max_length=6000)
    """The final assistant message the user will see."""


class DoneTool:
    """Terminate the agent loop with a final message to the user."""

    name: str = "done"
    description: str = (
        "Signal the task is complete. Provide `final_text` — a concise "
        "summary of what was done and the key result. No further tools "
        "will be called after this."
    )
    args_schema: type[BaseModel] = DoneArgs

    async def run(self, args: DoneArgs, ctx: ToolContext) -> ToolResult:  # noqa: ARG002
        # The loop inspects the ToolCall name before invoking this —
        # calling it directly is still safe and just echoes final_text.
        return tool_ok(
            args.final_text or "Task completed.",
            data={"final_text": args.final_text},
        )


__all__ = [
    "AskUserTool",
    "AskUserArgs",
    "AskUserOption",
    "TodoWriteTool",
    "TodoWriteArgs",
    "ListTargetsTool",
    "ListTargetsArgs",
    "RememberTool",
    "RememberArgs",
    "DoneTool",
    "DoneArgs",
]
