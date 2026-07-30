"""Tests for Full-agent mid-run replan guidance and budget profiles."""

from __future__ import annotations

from servers.agents.agent_runtime_guidance import (
    FULL_BUDGET_PROFILES,
    count_consecutive_tool_failures,
    mid_run_replan_message,
    resolve_budget_profile,
    should_inject_mid_run_replan,
)


def test_mid_run_replan_triggers_at_half_budget():
    assert should_inject_mid_run_replan(
        iteration=20,
        max_iterations=40,
        consecutive_failures=0,
        already_injected=False,
    )
    assert not should_inject_mid_run_replan(
        iteration=19,
        max_iterations=40,
        consecutive_failures=0,
        already_injected=False,
    )
    assert not should_inject_mid_run_replan(
        iteration=20,
        max_iterations=40,
        consecutive_failures=0,
        already_injected=True,
    )


def test_mid_run_replan_triggers_on_consecutive_failures():
    assert should_inject_mid_run_replan(
        iteration=4,
        max_iterations=40,
        consecutive_failures=2,
        already_injected=False,
    )
    assert not should_inject_mid_run_replan(
        iteration=2,
        max_iterations=40,
        consecutive_failures=2,
        already_injected=False,
    )


def test_mid_run_replan_message_russian_and_actionable():
    msg = mid_run_replan_message(iterations_used=20, iterations_max=40, consecutive_failures=2)
    assert "MID-RUN REPLAN" in msg
    assert "20/40" in msg
    assert "ACTION" in msg
    assert "ошибкой" in msg or "failed" in msg.lower() or "не повторяй" in msg


def test_count_consecutive_tool_failures():
    log = [
        {"result": "ok exit_code=0"},
        {"result": "Blocked: dangerous"},
        {"result": "SSH error: timeout"},
    ]
    assert count_consecutive_tool_failures(log) == 2
    assert count_consecutive_tool_failures([{"result": "all good exit_code=0"}]) == 0


def test_budget_profiles_complex_above_standard():
    quick = resolve_budget_profile("quick")
    standard = resolve_budget_profile("standard")
    complex_p = resolve_budget_profile("complex")
    assert quick and standard and complex_p
    assert complex_p["max_iterations"] > standard["max_iterations"]
    assert complex_p["session_timeout_seconds"] > standard["session_timeout_seconds"]
    assert FULL_BUDGET_PROFILES["standard"]["max_iterations"] == 40
    assert resolve_budget_profile("nope") is None


def test_agent_engine_runner_wires_mid_run_replan():
    import inspect

    from servers.agents import agent_engine_runner

    src = inspect.getsource(agent_engine_runner.run_agent_engine)
    assert "should_inject_mid_run_replan" in src
    assert "mid_run_replan_message" in src
    assert "_mid_run_replan_injected" in src
