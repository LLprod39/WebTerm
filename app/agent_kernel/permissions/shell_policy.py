"""Compatibility facade for shared read-only shell classification."""

from app.shell_commands import is_read_only_analysis, is_read_only_command

__all__ = ["is_read_only_analysis", "is_read_only_command"]
