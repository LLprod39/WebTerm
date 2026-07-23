"""Pure helpers for terminal-AI command outcomes."""

from __future__ import annotations


def unavailable_command_name(command: str, exit_code: int | None) -> str:
    """Return the base command name for exit=127 outcomes."""
    if exit_code != 127:
        return ""
    command_text = str(command or "").strip()
    if not command_text:
        return ""
    return command_text.split()[0].split("/")[-1]
