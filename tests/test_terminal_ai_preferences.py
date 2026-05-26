from __future__ import annotations

from servers.services.terminal_ai.preferences import (
    clone_ai_settings,
    default_ai_settings,
    is_auto_report_enabled,
    normalize_ai_chat_mode,
    normalize_ai_settings,
    normalize_int_list,
    normalize_pattern_list,
    parse_bool,
)


def test_default_ai_settings_returns_independent_copy() -> None:
    first = default_ai_settings()
    second = default_ai_settings()

    first["allowlist_patterns"].append("ls")

    assert second["allowlist_patterns"] == []
    assert second["memory_ttl_requests"] == 6


def test_normalize_ai_settings_clamps_ttl_and_sanitizes_lists() -> None:
    normalized = normalize_ai_settings(
        {
            "memory_enabled": "off",
            "memory_ttl_requests": 99,
            "auto_report": "bad",
            "confirm_dangerous_commands": "0",
            "allowlist_patterns": "ls\nLS\n pwd ",
            "blocklist_patterns": [" rm -rf / ", "", "RM -RF /"],
            "dry_run": "yes",
            "extra_target_server_ids": [1, "2", 2, 0, -1, "bad", 3, 4, 5, 6],
            "nova_session_context_enabled": "false",
            "nova_recent_activity_enabled": "on",
        }
    )

    assert normalized["memory_enabled"] is False
    assert normalized["memory_ttl_requests"] == 20
    assert normalized["auto_report"] == "auto"
    assert normalized["confirm_dangerous_commands"] is False
    assert normalized["allowlist_patterns"] == ["ls", "pwd"]
    assert normalized["blocklist_patterns"] == ["rm -rf /"]
    assert normalized["dry_run"] is True
    assert normalized["extra_target_server_ids"] == [1, 2, 3, 4, 5]
    assert normalized["nova_session_context_enabled"] is False
    assert normalized["nova_recent_activity_enabled"] is True


def test_primitive_normalizers() -> None:
    assert parse_bool(True) is True
    assert parse_bool(None, True) is True
    assert parse_bool("yes") is True
    assert parse_bool("false") is False
    assert normalize_pattern_list([" A ", "a", "B"]) == ["A", "B"]
    assert normalize_int_list([1, "1", "2", 0, -5, "x"]) == [1, 2]


def test_clone_and_mode_helpers() -> None:
    cloned = clone_ai_settings({"dry_run": True, "extra_target_server_ids": ["7", "7", 8]})
    assert cloned["dry_run"] is True
    assert cloned["extra_target_server_ids"] == [7, 8]
    assert is_auto_report_enabled({"auto_report": "on"}, "fast") is True
    assert is_auto_report_enabled({"auto_report": "off"}, "step") is False
    assert is_auto_report_enabled({"auto_report": "auto"}, "step") is True
    assert is_auto_report_enabled({"auto_report": "auto"}, "fast") is False
    assert normalize_ai_chat_mode("ASK") == "ask"
    assert normalize_ai_chat_mode("bad") == "agent"
