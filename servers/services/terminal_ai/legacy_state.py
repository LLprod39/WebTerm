"""Compatibility bridge between legacy consumer attrs and TerminalAiSession."""

from __future__ import annotations

from typing import Any

from servers.services.terminal_ai.session import TerminalAiSession


def sync_legacy_ai_queue_state(
    owner: Any,
    session_cls: type[TerminalAiSession] = TerminalAiSession,
) -> TerminalAiSession:
    """Mirror historical consumer request-state attributes into a session."""
    ai_session = getattr(owner, "_ai_session", None)
    if ai_session is None:
        ai_session = session_cls()
        owner._ai_session = ai_session
    ai_session.plan = getattr(owner, "_ai_plan", [])
    ai_session.plan_index = int(getattr(owner, "_ai_plan_index", 0) or 0)
    ai_session.next_id = int(getattr(owner, "_ai_next_id", 1) or 1)
    ai_session.step_extra_count = int(getattr(owner, "_ai_step_extra_count", 0) or 0)
    ai_session.forbidden_patterns = list(getattr(owner, "_ai_forbidden_patterns", []) or [])
    ai_session.user_message = str(getattr(owner, "_ai_user_message", "") or "")
    ai_session.chat_mode = str(getattr(owner, "_ai_chat_mode", "agent") or "agent")
    ai_session.execution_mode = str(getattr(owner, "_ai_execution_mode", "step") or "step")
    ai_session.run_id = str(getattr(owner, "_ai_run_id", "") or "")
    ai_session.marker_token = str(getattr(owner, "_ai_marker_token", "") or "")
    ai_session.last_done_items = getattr(owner, "_ai_last_done_items", [])
    ai_session.last_report = str(getattr(owner, "_ai_last_report", "") or "")
    ai_session.stop_requested = bool(getattr(owner, "_ai_stop_requested", False))
    return ai_session


def apply_legacy_ai_queue_state(owner: Any, ai_session: TerminalAiSession) -> None:
    """Mirror a TerminalAiSession request-state back into historical attrs."""
    owner._ai_plan, owner._ai_plan_index = ai_session.plan, ai_session.plan_index
    owner._ai_next_id, owner._ai_step_extra_count = ai_session.next_id, ai_session.step_extra_count
    owner._ai_forbidden_patterns = list(ai_session.forbidden_patterns)
    owner._ai_user_message = ai_session.user_message
    owner._ai_chat_mode = ai_session.chat_mode
    owner._ai_execution_mode = ai_session.execution_mode
    owner._ai_run_id = ai_session.run_id
    owner._ai_marker_token = ai_session.marker_token
    owner._ai_last_done_items = ai_session.last_done_items
    owner._ai_last_report = ai_session.last_report
    owner._ai_stop_requested = ai_session.stop_requested
