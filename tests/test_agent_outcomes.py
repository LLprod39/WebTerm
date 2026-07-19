from __future__ import annotations

from app.agent_kernel.runtime.outcomes import (
    EXIT_EMPTY_LLM,
    EXIT_FINAL_ANSWER,
    EXIT_MAX_ITERATIONS,
    EXIT_TIMEOUT,
    ON_PARTIAL_ABORT,
    ON_PARTIAL_SUCCESS,
    map_agent_outcome_to_pipeline_state,
    resolve_multi_agent_outcome,
    resolve_react_outcome,
)


def test_react_timeout_is_failed():
    outcome = resolve_react_outcome(
        exit_reason=EXIT_TIMEOUT,
        tool_calls=[{"tool": "ssh_execute"}],
        tools_available=True,
    )
    assert outcome.outcome == "failed"
    assert outcome.status == "failed"


def test_react_max_iterations_is_partial_completed():
    outcome = resolve_react_outcome(
        exit_reason=EXIT_MAX_ITERATIONS,
        tool_calls=[{"tool": "ssh_execute"}, {"tool": "read_console"}],
        tools_available=True,
    )
    assert outcome.outcome == "partial"
    assert outcome.status == "completed"
    assert outcome.tool_call_count == 2


def test_react_final_answer_without_tools_is_partial():
    outcome = resolve_react_outcome(
        exit_reason=EXIT_FINAL_ANSWER,
        tool_calls=[],
        tools_available=True,
    )
    assert outcome.outcome == "partial"
    assert outcome.status == "completed"


def test_react_final_answer_with_tools_is_success():
    outcome = resolve_react_outcome(
        exit_reason=EXIT_FINAL_ANSWER,
        tool_calls=[{"tool": "ssh_execute"}],
        tools_available=True,
    )
    assert outcome.outcome == "success"
    assert outcome.status == "completed"


def test_react_pending_verification_is_partial():
    outcome = resolve_react_outcome(
        exit_reason=EXIT_FINAL_ANSWER,
        tool_calls=[{"tool": "ssh_execute"}],
        tools_available=True,
        pending_verifications={"service_verification"},
    )
    assert outcome.outcome == "partial"
    assert "service_verification" in outcome.pending_verifications


def test_react_empty_llm_without_tools_is_failed():
    outcome = resolve_react_outcome(
        exit_reason=EXIT_EMPTY_LLM,
        tool_calls=[],
        tools_available=True,
    )
    assert outcome.outcome == "failed"
    assert outcome.status == "failed"


def test_multi_failed_tasks_not_silent_completed():
    outcome = resolve_multi_agent_outcome(
        stop_requested=False,
        plan_tasks=[
            {"status": "done", "iterations": [{}]},
            {"status": "failed", "error": "boom", "iterations": []},
        ],
    )
    assert outcome.outcome == "partial"
    assert outcome.status == "completed"
    assert outcome.failed_task_count == 1
    assert outcome.done_task_count == 1


def test_multi_all_failed_is_failed():
    outcome = resolve_multi_agent_outcome(
        stop_requested=False,
        plan_tasks=[
            {"status": "failed", "error": "a"},
            {"status": "failed", "error": "b"},
        ],
    )
    assert outcome.outcome == "failed"
    assert outcome.status == "failed"


def test_multi_abort_is_failed():
    outcome = resolve_multi_agent_outcome(
        stop_requested=False,
        plan_tasks=[
            {"status": "done"},
            {"status": "failed", "orchestrator_decision": {"action": "abort", "reason": "no"}},
            {"status": "pending"},
        ],
    )
    assert outcome.outcome == "failed"
    assert outcome.status == "failed"


def test_multi_all_skipped_is_failed():
    outcome = resolve_multi_agent_outcome(
        stop_requested=False,
        plan_tasks=[
            {"status": "skipped", "error": "Session timeout"},
            {"status": "skipped", "error": "Session timeout"},
        ],
    )
    assert outcome.outcome == "failed"
    assert outcome.status == "failed"


def test_multi_all_done_is_success():
    outcome = resolve_multi_agent_outcome(
        stop_requested=False,
        plan_tasks=[{"status": "done"}, {"status": "done"}],
    )
    assert outcome.outcome == "success"
    assert outcome.status == "completed"


def test_pipeline_maps_partial_default_to_failed():
    state = map_agent_outcome_to_pipeline_state(
        outcome="partial",
        agent_status="completed",
        final_report="half done",
        ai_analysis="",
        agent_run_id=1,
        outcome_reason="Max iterations exhausted",
        tool_call_count=3,
    )
    assert state["status"] == "failed"
    assert state["outcome"] == "partial"
    assert state["output"] == "half done"
    assert "Max iterations" in state["error"]
    assert state["tool_call_count"] == 3


def test_pipeline_maps_partial_on_partial_success():
    state = map_agent_outcome_to_pipeline_state(
        outcome="partial",
        agent_status="completed",
        final_report="half done",
        ai_analysis="",
        agent_run_id=1,
        on_partial=ON_PARTIAL_SUCCESS,
        outcome_reason="partial work",
    )
    assert state["status"] == "completed"
    assert state["outcome"] == "partial"
    assert state["error"] == ""


def test_pipeline_maps_partial_abort():
    state = map_agent_outcome_to_pipeline_state(
        outcome="partial",
        agent_status="completed",
        final_report="half done",
        ai_analysis="",
        agent_run_id=1,
        on_partial=ON_PARTIAL_ABORT,
    )
    assert state["status"] == "failed"
    assert state["on_partial"] == "abort"


def test_pipeline_maps_success_and_stopped():
    ok = map_agent_outcome_to_pipeline_state(
        outcome="success",
        agent_status="completed",
        final_report="done",
        ai_analysis="",
        agent_run_id=9,
    )
    assert ok["status"] == "completed"
    assert ok["error"] == ""

    stopped = map_agent_outcome_to_pipeline_state(
        outcome="stopped",
        agent_status="stopped",
        final_report="",
        ai_analysis="stopped",
        agent_run_id=9,
        outcome_reason="Agent stopped by operator",
    )
    assert stopped["status"] == "stopped"


def test_pipeline_backcompat_without_outcome_uses_status():
    state = map_agent_outcome_to_pipeline_state(
        outcome="",
        agent_status="completed",
        final_report="legacy",
        ai_analysis="",
        agent_run_id=3,
    )
    assert state["status"] == "completed"
    assert state["outcome"] == "success"
