"""Unit tests for shared model-driven agentic loop policy."""

from __future__ import annotations

from app.core.agentic_loop_policy import (
    MAX_GOAL_SELF_CHECKS,
    assistant_called_finish_tool,
    messages_have_host_mention,
    should_goal_self_check,
)


def test_host_mention_detection():
    assert messages_have_host_mention("глянь что с @grafana-01")
    assert messages_have_host_mention("check @host-1 please")
    assert not messages_have_host_mention("Привет")
    assert not messages_have_host_mention("Список серверов")


def test_self_check_requires_tools_without_evidence():
    assert should_goal_self_check(
        tools_executed=True,
        self_checks_used=0,
        has_task_evidence=False,
        inventory_only=True,
        host_ops_goal=False,
        host_mention=True,
    )
    # Greeting / no tools → never.
    assert not should_goal_self_check(
        tools_executed=False,
        self_checks_used=0,
        has_task_evidence=False,
        inventory_only=False,
        host_ops_goal=True,
        host_mention=True,
    )
    # Already have SSH evidence → final answer ok.
    assert not should_goal_self_check(
        tools_executed=True,
        self_checks_used=0,
        has_task_evidence=True,
        inventory_only=False,
        host_ops_goal=True,
        host_mention=True,
    )
    # Cap self-checks.
    assert not should_goal_self_check(
        tools_executed=True,
        self_checks_used=MAX_GOAL_SELF_CHECKS,
        has_task_evidence=False,
        inventory_only=True,
        host_ops_goal=True,
        host_mention=True,
    )


def test_finish_tool_name_shapes():
    assert assistant_called_finish_tool([{"name": "operator_finish_report"}])
    assert assistant_called_finish_tool([{"name": "operator.finish_report"}])
    assert not assistant_called_finish_tool([{"name": "operator_resolve_server"}])
