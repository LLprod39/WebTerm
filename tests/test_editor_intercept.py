"""
Unit tests for servers.services.editor_intercept helpers.

Regression coverage for the bug where bare TUI invocations (e.g. ``nano`` with
no file argument) were not detected as interactive programs. The SSH terminal
consumer then wrapped them with an exit-code marker command, whose bytes were
delivered as keystrokes to the running TUI (not the shell), corrupting the UI
and making the terminal appear frozen (Ctrl+X / arrow keys stopped working
until the tab was closed).
"""

from __future__ import annotations

import pytest

from servers.consumers.ssh_terminal import SSHTerminalConsumer
from servers.services.editor_intercept import (
    detect_editor_command,
    is_interactive_tui_command,
)


class TestIsInteractiveTuiCommand:
    @pytest.mark.parametrize(
        "command",
        [
            "nano",
            "  nano  ",
            "nano /etc/hosts",
            "nano -w /tmp/file",
            "sudo nano",
            "sudo  nano /etc/hosts",
            "vim",
            "vi /tmp/f",
            "emacs",
            "less /var/log/syslog",
            "more README",
            "man ls",
            "top",
            "htop",
            "btop",
            "watch -n 1 date",
            "tmux",
            "screen",
        ],
    )
    def test_detects_tui(self, command: str) -> None:
        assert is_interactive_tui_command(command) is True

    @pytest.mark.parametrize(
        "command",
        [
            "",
            "   ",
            "ls -la",
            "echo nano",            # literal, not invocation
            "nanorc --help",        # different binary, prefix-only match would be wrong
            "topdump",              # prefix-only match would be wrong
            "vimdiff a b",          # not in the whitelist (distinct program)
            "cat /etc/hosts",
            "sudo systemctl status nginx",
            "python3 -c 'print(1)'",
        ],
    )
    def test_ignores_non_tui(self, command: str) -> None:
        assert is_interactive_tui_command(command) is False


class TestShouldUseManualCommandMarker:
    """
    ``_should_use_manual_command_marker`` decides whether the consumer wraps a
    typed command with an exit-code probe. For TUI programs it MUST return
    False: otherwise the probe is injected into the running TUI as keystrokes.
    """

    @pytest.mark.parametrize(
        "command",
        [
            "nano",
            "nano /etc/hosts",
            "sudo nano /etc/hosts",
            "vim",
            "less /var/log/syslog",
            "man ls",
            "top",
            "htop",
            "tmux",
        ],
    )
    def test_tui_commands_skip_marker(self, command: str) -> None:
        assert SSHTerminalConsumer._should_use_manual_command_marker(command) is False

    @pytest.mark.parametrize(
        "command",
        [
            "ls -la",
            "echo hello",
            "cat /etc/hosts",
            "systemctl status nginx",
        ],
    )
    def test_regular_commands_still_marker(self, command: str) -> None:
        assert SSHTerminalConsumer._should_use_manual_command_marker(command) is True


class TestDetectEditorCommandUnchanged:
    """
    The new TUI helper must not change the behaviour of ``detect_editor_command``:
    bare editor invocations (no file argument) still return None so the GUI
    modal is not triggered for them — they are simply allowed to run in the
    terminal without marker wrapping.
    """

    def test_bare_nano_not_intercepted(self) -> None:
        assert detect_editor_command("nano") is None

    def test_nano_with_path_intercepted(self) -> None:
        info = detect_editor_command("nano /etc/hosts")
        assert info is not None
        assert info["editor"] == "nano"
        assert info["path"] == "/etc/hosts"
        assert info["sudo"] is False

    def test_sudo_nano_with_path_intercepted(self) -> None:
        info = detect_editor_command("sudo nano /etc/hosts")
        assert info is not None
        assert info["editor"] == "nano"
        assert info["path"] == "/etc/hosts"
        assert info["sudo"] is True
