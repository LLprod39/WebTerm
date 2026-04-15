"""
Safety helpers for tool execution.
"""
import re

_DANGEROUS_CMD_PATTERNS = [
    r"\brm\s+-rf\b",
    r"\brm\s+-r\b",
    r"\bmkfs\.\w+\b",
    r"\bmkfs\b",
    r"\bdd\s+if=",
    r"\bshutdown\b",
    r"\breboot\b",
    r"\bsystemctl\s+(stop|disable|mask|poweroff|halt)\b",
    r"\bservice\s+.+\s+stop\b",
    r"\btruncate\s+-s\s+0\b",
]


def is_dangerous_command(command: str) -> bool:
    if not command:
        return False
    cmd = command.lower()
    return any(re.search(pattern, cmd) for pattern in _DANGEROUS_CMD_PATTERNS)
