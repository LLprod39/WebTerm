from __future__ import annotations

from servers.services.terminal_input import (
    build_shell_exports,
    capture_completed_terminal_commands,
    detect_install_error,
    is_install_command,
    is_streaming_command,
    normalize_manual_command_output,
    parse_terminal_size,
    should_use_manual_command_marker,
    strip_ansi_and_controls,
)


def test_capture_completed_terminal_commands_preserves_buffer_between_chunks() -> None:
    first = capture_completed_terminal_commands("ec", buffer="")
    assert first.buffer == "ec"
    assert first.commands == []

    second = capture_completed_terminal_commands("ho hi\r", buffer=first.buffer)
    assert second.buffer == ""
    assert second.commands == ["echo hi"]


def test_capture_completed_terminal_commands_handles_backspace_and_ctrl_u() -> None:
    captured = capture_completed_terminal_commands("abc\bZ\nkeep\x15drop\n", buffer="")
    assert captured.buffer == ""
    assert captured.commands == ["abZ", "drop"]


def test_manual_command_marker_skips_tui_and_unfinished_shell_syntax() -> None:
    assert should_use_manual_command_marker("nano /etc/hosts") is False
    assert should_use_manual_command_marker("echo ok &&") is False
    assert should_use_manual_command_marker("if test -f /tmp/x") is False
    assert should_use_manual_command_marker("systemctl status nginx") is True


def test_command_classification_helpers() -> None:
    assert is_streaming_command("tail -f /var/log/syslog") is True
    assert is_streaming_command("top") is True
    assert is_streaming_command("ls -la") is False
    assert is_install_command("npm install") is True
    assert is_install_command("python manage.py test") is False
    assert detect_install_error("npm ERR! missing package") is True


def test_terminal_size_and_exports_are_sanitized() -> None:
    assert parse_terminal_size({"cols": 999, "rows": 1}).cols == 400
    assert parse_terminal_size({"cols": 999, "rows": 1}).rows == 5

    exports = build_shell_exports({"GOOD": "a b", "BAD-NAME": "x", "MULTI": "a\nb"})
    assert "export GOOD='a b'" in exports
    assert "BAD-NAME" not in exports
    assert "export MULTI='a b'" in exports


def test_manual_command_output_cleanup() -> None:
    raw = "\x1b[32mecho hi\x1b[0m\r\nhi\n\x07"
    assert strip_ansi_and_controls(raw).replace("\r", "") == "echo hi\nhi\n"
    assert normalize_manual_command_output("echo hi", raw) == "hi"
