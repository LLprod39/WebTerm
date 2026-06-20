"""Tests for the Terminal AI legacy state bridge."""

from __future__ import annotations

from types import SimpleNamespace

from servers.services.terminal_ai.legacy_state import (
    apply_legacy_ai_queue_state,
    sync_legacy_ai_queue_state,
)
from servers.services.terminal_ai.session import TerminalAiSession


def test_sync_legacy_ai_queue_state_creates_session_from_consumer_attrs():
    owner = SimpleNamespace(
        _ai_plan=[{"id": 1}],
        _ai_plan_index=1,
        _ai_next_id=8,
        _ai_step_extra_count=2,
        _ai_forbidden_patterns=["rm -rf", "mkfs"],
        _ai_user_message="deploy",
        _ai_chat_mode="ask",
        _ai_execution_mode="fast",
        _ai_run_id="run-1",
        _ai_marker_token="marker-1",
        _ai_last_done_items=[{"id": 1, "exit_code": 0}],
        _ai_last_report="done",
        _ai_stop_requested=True,
    )

    session = sync_legacy_ai_queue_state(owner)

    assert owner._ai_session is session
    assert session.plan == [{"id": 1}]
    assert session.plan_index == 1
    assert session.next_id == 8
    assert session.step_extra_count == 2
    assert session.forbidden_patterns == ["rm -rf", "mkfs"]
    assert session.user_message == "deploy"
    assert session.chat_mode == "ask"
    assert session.execution_mode == "fast"
    assert session.run_id == "run-1"
    assert session.marker_token == "marker-1"
    assert session.last_done_items == [{"id": 1, "exit_code": 0}]
    assert session.last_report == "done"
    assert session.stop_requested is True


def test_apply_legacy_ai_queue_state_updates_consumer_attrs():
    owner = SimpleNamespace()
    session = TerminalAiSession(
        plan=[{"id": 5}],
        plan_index=1,
        next_id=6,
        step_extra_count=3,
        forbidden_patterns=["shutdown"],
        user_message="inspect logs",
        chat_mode="agent",
        execution_mode="step",
        run_id="run-2",
        marker_token="marker-2",
        last_done_items=[{"id": 5, "exit_code": 1}],
        last_report="needs attention",
        stop_requested=True,
    )

    apply_legacy_ai_queue_state(owner, session)

    assert owner._ai_plan == [{"id": 5}]
    assert owner._ai_plan_index == 1
    assert owner._ai_next_id == 6
    assert owner._ai_step_extra_count == 3
    assert owner._ai_forbidden_patterns == ["shutdown"]
    assert owner._ai_user_message == "inspect logs"
    assert owner._ai_chat_mode == "agent"
    assert owner._ai_execution_mode == "step"
    assert owner._ai_run_id == "run-2"
    assert owner._ai_marker_token == "marker-2"
    assert owner._ai_last_done_items == [{"id": 5, "exit_code": 1}]
    assert owner._ai_last_report == "needs attention"
    assert owner._ai_stop_requested is True


def test_clear_through_legacy_sync_preserves_request_context():
    owner = SimpleNamespace(
        _ai_plan=[{"id": 1}],
        _ai_plan_index=1,
        _ai_next_id=9,
        _ai_step_extra_count=4,
        _ai_forbidden_patterns=["reboot"],
        _ai_user_message="deploy",
        _ai_chat_mode="agent",
        _ai_execution_mode="step",
        _ai_run_id="run-3",
        _ai_marker_token="marker-3",
        _ai_last_done_items=[{"id": 1}],
        _ai_last_report="partial",
        _ai_stop_requested=True,
    )

    session = sync_legacy_ai_queue_state(owner)
    session.clear()
    apply_legacy_ai_queue_state(owner, session)

    assert owner._ai_plan == []
    assert owner._ai_plan_index == 0
    assert owner._ai_step_extra_count == 0
    assert owner._ai_forbidden_patterns == []
    assert owner._ai_stop_requested is False
    assert owner._ai_run_id == "run-3"
    assert owner._ai_marker_token == "marker-3"
    assert owner._ai_user_message == "deploy"
    assert owner._ai_last_done_items == [{"id": 1}]
    assert owner._ai_last_report == "partial"
