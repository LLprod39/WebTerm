"""
Typed-ish WebSocket event builders for terminal consumers.

The transport still sends plain JSON dictionaries, but all new code should
construct common ``ai_*`` payloads through these helpers instead of hand-rolled
dicts spread across the consumer.
"""

from __future__ import annotations

from typing import Any

TerminalEvent = dict[str, Any]


def ai_status(status: str, **fields: Any) -> TerminalEvent:
    return {"type": "ai_status", "status": status, **_compact(fields)}


def ai_error(message: str, **fields: Any) -> TerminalEvent:
    return {"type": "ai_error", "message": str(message or ""), **_compact(fields)}


def ai_response(
    *,
    assistant_text: str,
    mode: str = "answer",
    commands: list[dict[str, Any]] | None = None,
    execution_mode: str | None = None,
    **fields: Any,
) -> TerminalEvent:
    payload: TerminalEvent = {
        "type": "ai_response",
        "mode": mode,
        "assistant_text": str(assistant_text or ""),
        "commands": list(commands or []),
    }
    if execution_mode is not None:
        payload["execution_mode"] = execution_mode
    payload.update(_compact(fields))
    return payload


def ai_command_status(
    *,
    item_id: int,
    status: str,
    exit_code: int | None = None,
    reason: str | None = None,
    streaming: bool | None = None,
    **fields: Any,
) -> TerminalEvent:
    payload: TerminalEvent = {
        "type": "ai_command_status",
        "id": int(item_id),
        "status": status,
    }
    if exit_code is not None:
        payload["exit_code"] = exit_code
    if reason:
        payload["reason"] = reason
    if streaming is not None:
        payload["streaming"] = streaming
    payload.update(_compact(fields))
    return payload


def ai_parallel_batch(*, status: str, ids: list[int], count: int | None = None) -> TerminalEvent:
    return {
        "type": "ai_parallel_batch",
        "status": status,
        "ids": [int(item_id) for item_id in ids],
        "count": int(count if count is not None else len(ids)),
    }


def ai_install_progress(*, command: str, elapsed: int, output_tail: str) -> TerminalEvent:
    return {
        "type": "ai_install_progress",
        "cmd": str(command or ""),
        "elapsed": int(elapsed),
        "output_tail": str(output_tail or "")[:200],
    }


def ai_report(*, report: str, status: str) -> TerminalEvent:
    return {"type": "ai_report", "report": str(report or ""), "status": status}


def ai_explanation(*, item_id: Any, command: str, explanation: str) -> TerminalEvent:
    return {
        "type": "ai_explanation",
        "id": item_id,
        "cmd": str(command or ""),
        "explanation": str(explanation or ""),
    }


def ai_direct_output(
    *,
    item_id: int,
    command: str,
    output: str,
    exit_code: int,
    dry_run: bool = False,
) -> TerminalEvent:
    return {
        "type": "ai_direct_output",
        "id": int(item_id),
        "cmd": str(command or ""),
        "output": str(output or ""),
        "exit_code": int(exit_code),
        "dry_run": bool(dry_run),
    }


def ai_recovery(
    *,
    original_cmd: str,
    new_cmd: str,
    new_id: int,
    why: str,
    requires_confirm: bool,
    reason: str,
    streaming: bool,
) -> TerminalEvent:
    return {
        "type": "ai_recovery",
        "original_cmd": str(original_cmd or ""),
        "new_cmd": str(new_cmd or ""),
        "new_id": int(new_id),
        "why": str(why or ""),
        "requires_confirm": bool(requires_confirm),
        "reason": str(reason or ""),
        "streaming": bool(streaming),
    }


def ai_question(*, q_id: str, question: str, command: str, exit_code: int | None) -> TerminalEvent:
    return {
        "type": "ai_question",
        "q_id": str(q_id or ""),
        "question": str(question or ""),
        "cmd": str(command or ""),
        "exit_code": exit_code,
    }


def _compact(fields: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in fields.items() if value is not None}
