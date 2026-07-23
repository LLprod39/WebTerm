from __future__ import annotations

from typing import Any

from servers.services.terminal_ai.active_command import append_active_output
from servers.services.terminal_ai.session_context import apply_successful_command_context
from servers.services.terminal_stream_state import append_clean_output


def append_terminal_tail(consumer: Any, text: str) -> None:
    consumer._terminal_tail = append_clean_output(consumer._terminal_tail, text, limit=8000)


def append_ai_output(consumer: Any, text: str) -> None:
    append_active_output(consumer, text)


def append_manual_output(consumer: Any, text: str) -> None:
    if not text:
        return
    if getattr(consumer, "_manual_active_cmd_id", None) is None:
        return
    consumer._manual_active_output = append_clean_output(consumer._manual_active_output, text, limit=12000)


async def finalize_manual_terminal_command(consumer: Any, cmd_id: int, exit_code: int, *, persist_result: Any) -> None:
    pending = list(getattr(consumer, "_manual_pending_commands", []) or [])
    if not pending:
        return

    item = next((entry for entry in pending if int(entry.get("id") or 0) == int(cmd_id)), None)
    if item is None:
        return

    raw_output = (
        consumer._manual_active_output if int(getattr(consumer, "_manual_active_cmd_id", 0) or 0) == int(cmd_id) else ""
    )
    clean_output = consumer._normalize_manual_command_output(str(item.get("command") or ""), raw_output)
    await persist_result(
        user_id=int(item.get("user_id") or 0),
        server_id=int(item.get("server_id") or 0),
        session_id=str(item.get("session_id") or ""),
        command=str(item.get("command") or ""),
        output=clean_output,
        exit_code=int(exit_code),
        cwd=str(item.get("cwd") or ""),
    )
    consumer._append_nova_recent_activity(
        command=str(item.get("command") or ""),
        cwd=str(item.get("cwd") or ""),
        exit_code=int(exit_code),
        source="live_session",
    )
    context_before = getattr(consumer, "_nova_session_context", {}) or dict(item.get("context_before") or {})
    old_cwd = str(context_before.get("cwd") or item.get("cwd") or "")
    consumer._nova_session_context = apply_successful_command_context(
        context_before,
        command=str(item.get("command") or ""),
        exit_code=int(exit_code),
    )
    new_cwd = str((consumer._nova_session_context or {}).get("cwd") or "")
    if new_cwd and new_cwd != old_cwd:
        await consumer._emit_terminal_session()

    consumer._manual_pending_commands = [entry for entry in pending if int(entry.get("id") or 0) != int(cmd_id)]
    if int(getattr(consumer, "_manual_active_cmd_id", 0) or 0) == int(cmd_id):
        consumer._manual_active_cmd_id = None
        consumer._manual_active_output = ""
    if consumer._manual_active_cmd_id is None and consumer._manual_pending_commands:
        consumer._manual_active_cmd_id = int(consumer._manual_pending_commands[0].get("id") or 0) or None
        consumer._manual_active_output = ""
