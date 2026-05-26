from __future__ import annotations

from servers.services.terminal_ai.plan_items import (
    build_plan_item,
    normalize_command_text,
    normalize_execution_mode,
    resolve_auto_execution_mode,
)


def test_normalize_execution_mode_aliases():
    assert normalize_execution_mode("smart") == "auto"
    assert normalize_execution_mode("step-by-step") == "step"
    assert normalize_execution_mode("batch") == "fast"
    assert normalize_execution_mode("nova") == "agent"
    assert normalize_execution_mode("unknown") == "step"


def test_resolve_auto_execution_mode_prefers_planner_mode():
    assert (
        resolve_auto_execution_mode(
            plan_obj={"execution_mode": "fast"},
            commands_raw=[{"cmd": "x"} for _ in range(5)],
            user_message="restart prod",
        )
        == "fast"
    )


def test_resolve_auto_execution_mode_short_plan_fast():
    assert (
        resolve_auto_execution_mode(
            plan_obj={"execution_mode": "auto"},
            commands_raw=[{"cmd": "df -h"}],
            user_message="check disk",
        )
        == "fast"
    )


def test_resolve_auto_execution_mode_danger_hint_step():
    assert (
        resolve_auto_execution_mode(
            plan_obj={"execution_mode": "auto"},
            commands_raw=[{"cmd": "x"} for _ in range(3)],
            user_message="upgrade production nginx",
        )
        == "step"
    )


def test_normalize_command_text_uses_memory_heuristic_normalizer():
    assert normalize_command_text("  ls -la  ") == "ls -la"
    assert normalize_command_text("") == ""


def test_build_plan_item_shapes_policy_fields():
    item = build_plan_item(
        item_id=7,
        command="tail -f /var/log/syslog",
        why="watch logs",
        chat_mode="ask",
        forbidden_patterns=[],
        allowlist_patterns=[],
        confirm_dangerous_commands=True,
        exec_mode="invalid",
    )

    assert item["id"] == 7
    assert item["cmd"] == "tail -f /var/log/syslog"
    assert item["why"] == "watch logs"
    assert item["requires_confirm"] is True
    assert item["blocked"] is False
    assert item["reason"] == "ask_mode"
    assert item["status"] == "pending"
    assert item["streaming"] is True
    assert item["exec_mode"] in {"pty", "direct"}


def test_build_plan_item_marks_forbidden_as_blocked():
    item = build_plan_item(
        item_id=1,
        command="rm -rf /",
        why="bad",
        chat_mode="agent",
        forbidden_patterns=["rm -rf /"],
    )

    assert item["blocked"] is True
    assert item["status"] == "blocked"
    assert item["reason"] == "forbidden"
