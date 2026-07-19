from __future__ import annotations

from studio.pipeline_context import (
    build_agent_upstream_context,
    inject_upstream_into_goal,
    require_agent_goal,
)


def test_require_agent_goal_rejects_empty():
    assert require_agent_goal("") is not None
    assert require_agent_goal("   ") is not None
    assert require_agent_goal("do something") is None


def test_build_agent_upstream_context_default_include():
    text = build_agent_upstream_context(
        {},
        {"n1": {"status": "completed", "output": "hello from n1"}},
    )
    assert "hello from n1" in text
    assert "n1" in text


def test_build_agent_upstream_context_opt_out():
    text = build_agent_upstream_context(
        {"include_upstream_outputs": False},
        {"n1": {"status": "completed", "output": "hello"}},
    )
    assert text == ""


def test_inject_upstream_into_goal_appends_section():
    goal = inject_upstream_into_goal("Investigate outage", "=== Output of node [a] ===\nCPU high")
    assert goal.startswith("Investigate outage")
    assert "## Context from previous pipeline steps" in goal
    assert "CPU high" in goal
