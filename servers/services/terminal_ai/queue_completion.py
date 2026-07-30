"""Post-queue completion flow for Terminal AI command runs."""

from __future__ import annotations

from typing import Any

from servers.services import terminal_events
from servers.services.terminal_ai.legacy_state import (
    apply_legacy_ai_queue_state,
    sync_legacy_ai_queue_state,
)
from servers.services.terminal_ai.memory import (
    select_memory_candidate_commands,
    should_extract_memory,
)
from servers.services.terminal_ai.reporter import (
    apply_dry_run_report_prefix,
    build_execution_summary,
)


async def handle_queue_completion(owner: Any) -> None:
    """Generate the final report/history/memory side effects for a command queue."""
    user_message = owner._ai_state.session.user_message
    async with owner._ai_state.lock:
        ai_session = sync_legacy_ai_queue_state(owner, owner._TerminalAiSessionCls)
        done_items = ai_session.snapshot_done_items()
        apply_legacy_ai_queue_state(owner, ai_session)

    done_with_output = owner._TerminalAiSessionCls.done_items_with_output(done_items)
    if not (user_message and done_items):
        return

    report = await _maybe_generate_report(owner, user_message=user_message, done_items=done_items)
    async with owner._ai_state.lock:
        owner._ai_state.session.last_report = report

    memory_enabled = bool(owner._ai_state.settings.get("memory_enabled", True))
    if memory_enabled:
        owner._add_to_history("assistant", build_execution_summary(done_items))
        if report:
            owner._add_to_history("assistant", f"[Отчёт]\n{report[:400]}")

    _maybe_spawn_memory_extraction(
        owner,
        user_message=user_message,
        done_items=done_items,
        done_with_output=done_with_output,
        report=report,
        memory_enabled=memory_enabled,
    )


async def _maybe_generate_report(owner: Any, *, user_message: str, done_items: list[dict[str, Any]]) -> str:
    settings = owner._ai_state.settings
    if not owner._is_auto_report_enabled(settings, owner._ai_state.session.execution_mode):
        return ""

    await owner._send_ai_event(terminal_events.ai_status("generating_report"))
    report = await owner._generate_ai_report_text(user_message, done_items)
    report = apply_dry_run_report_prefix(
        report,
        dry_run=bool(settings.get("dry_run", False)),
    )
    await owner._send_ai_event(
        terminal_events.ai_report(report=report, status=owner._compute_report_status(done_items))
    )
    return report


def _maybe_spawn_memory_extraction(
    owner: Any,
    *,
    user_message: str,
    done_items: list[dict[str, Any]],
    done_with_output: list[dict[str, Any]],
    report: str,
    memory_enabled: bool,
) -> None:
    memory_candidates = select_memory_candidate_commands(done_with_output)
    if (
        memory_candidates
        and should_extract_memory(done_items)
        and getattr(owner, "server", None)
        and getattr(owner, "_user_id", None)
        and memory_enabled
    ):
        owner._spawn_memory_extraction_task(
            user_message=user_message,
            commands_with_output=memory_candidates,
            report=report,
            user_id=int(owner._user_id),
            server_id=int(owner.server.id),
            audit_ctx=dict(owner._ai_state.audit_context),
        )
