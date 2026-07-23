"""Tests for terminal-AI command outcome helpers."""

from __future__ import annotations

from servers.services.terminal_ai.command_outcome import unavailable_command_name


def test_unavailable_command_name_returns_base_command_for_exit_127():
    assert unavailable_command_name("/usr/bin/python --version", 127) == "python"


def test_unavailable_command_name_ignores_non_127_exit_codes():
    assert unavailable_command_name("missing-tool --help", 1) == ""
    assert unavailable_command_name("missing-tool --help", 0) == ""
    assert unavailable_command_name("missing-tool --help", None) == ""


def test_unavailable_command_name_handles_empty_command():
    assert unavailable_command_name("", 127) == ""
    assert unavailable_command_name("   ", 127) == ""
