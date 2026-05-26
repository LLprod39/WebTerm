"""
Pure helpers for terminal input capture and command classification.

The SSH WebSocket consumer owns I/O, but the parsing rules here are pure
Python so they can be tested without Channels, AsyncSSH, or Django.
"""

from __future__ import annotations

import re
import shlex
from dataclasses import dataclass
from typing import Any

from servers.memory_heuristics import normalize_memory_command_text
from servers.services.editor_intercept import is_interactive_tui_command


@dataclass(frozen=True)
class TerminalSize:
    cols: int
    rows: int


@dataclass(frozen=True)
class TerminalInputCapture:
    buffer: str
    commands: list[str]


_STREAMING_CMD_RE = re.compile(
    r"(?:"
    r"\btail\s+.*-[a-zA-Z]*[fF]\b"
    r"|\btail\s+--follow\b"
    r"|\bjournalctl\s+.*(?:-[a-zA-Z]*[fF]\b|--follow\b)"
    r"|\bdocker\s+logs?\s+.*(?:-[a-zA-Z]*[fF]\b|--follow\b)"
    r"|\bkubectl\s+logs?\s+.*-[a-zA-Z]*[fF]\b"
    r"|\bpodman\s+logs?\s+.*(?:-[a-zA-Z]*[fF]\b|--follow\b)"
    r"|\bwatch\s+"
    r"|\btcpdump\b"
    r"|\bstrace\b"
    r"|\bping\s+(?!.*-c\s*\d)"
    r")",
    re.IGNORECASE,
)
_INTERACTIVE_CMDS = {
    "top",
    "htop",
    "iotop",
    "iftop",
    "nethogs",
    "vim",
    "vi",
    "nano",
    "less",
    "more",
    "man",
    "pstree",
    "glances",
}
_INSTALL_CMD_RE = re.compile(
    r"(?:"
    r"\bapt(?:-get)?\s+(?:install|upgrade|dist-upgrade)\b"
    r"|\byum\s+(?:install|update)\b"
    r"|\bdnf\s+(?:install|upgrade)\b"
    r"|\bpip[23]?\s+install\b"
    r"|\bnpm\s+(?:install|ci|i\b)"
    r"|\byarn\s+(?:install|add)\b"
    r"|\bdocker\s+(?:pull|build)\b"
    r"|\bcomposer\s+(?:install|update)\b"
    r"|\bcargo\s+(?:install|build)\b"
    r"|\bgo\s+(?:get|install|build)\b"
    r"|\bmake\s+(?:install|all|build)\b"
    r")",
    re.IGNORECASE,
)
_INSTALL_ERROR_RE = re.compile(
    r"(?:"
    r"E: Unable to locate package"
    r"|No such package|could not find package"
    r"|npm ERR!"
    r"|ERROR: Could not install"
    r"|error: could not"
    r"|Failed to fetch"
    r"|dpkg: error"
    r")",
    re.IGNORECASE,
)


def parse_terminal_size(content: dict[str, Any]) -> TerminalSize:
    try:
        cols = int(content.get("cols") or 80)
    except Exception:
        cols = 80
    try:
        rows = int(content.get("rows") or 24)
    except Exception:
        rows = 24
    return TerminalSize(cols=max(10, min(cols, 400)), rows=max(5, min(rows, 200)))


def build_shell_exports(env_vars: dict[str, Any]) -> str:
    exports: list[str] = []
    for key_raw, value_raw in (env_vars or {}).items():
        key = str(key_raw or "").strip()
        if not key or not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", key):
            continue
        value = str(value_raw if value_raw is not None else "").replace("\n", " ").replace("\r", " ").strip()
        exports.append(f"export {key}={shlex.quote(value)}")
    return "; ".join(exports)


def is_streaming_command(command: str) -> bool:
    """Return True when a command is expected to stream indefinitely or take over the PTY."""
    cleaned = (command or "").strip()
    if not cleaned:
        return False
    if _STREAMING_CMD_RE.search(cleaned):
        return True
    cmd_name = cleaned.split()[0].split("/")[-1].lower()
    return cmd_name in _INTERACTIVE_CMDS


def is_install_command(command: str) -> bool:
    """Return True for package/dependency install commands that can be long-running."""
    return bool(_INSTALL_CMD_RE.search(command or ""))


def detect_install_error(output: str) -> bool:
    """Return True if output clearly shows an install failure."""
    return bool(_INSTALL_ERROR_RE.search(output or ""))


def should_use_manual_command_marker(command: str) -> bool:
    normalized = normalize_memory_command_text(command)
    if not normalized:
        return False
    stripped = normalized.strip()
    lowered = stripped.lower()
    if not stripped:
        return False
    if is_interactive_tui_command(stripped):
        return False
    if "<<" in stripped or stripped.endswith("\\"):
        return False
    if re.search(r"(?:&&|\|\||\|)\s*$", stripped):
        return False
    if re.match(r"^\s*(if|for|while|until|case|select|function)\b", lowered):
        return False
    if re.search(r"\b(?:then|do|else|elif|in)\s*$", lowered):
        return False
    return not (stripped.count("'") % 2 or stripped.count('"') % 2 or stripped.count("`") % 2)


def strip_terminal_input_sequences(data: str) -> str:
    cleaned = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", data or "")
    return re.sub(r"\x1b.", "", cleaned)


def capture_completed_terminal_commands(data: str, *, buffer: str = "") -> TerminalInputCapture:
    cleaned = strip_terminal_input_sequences(data)
    if not cleaned:
        return TerminalInputCapture(buffer=str(buffer or ""), commands=[])

    command_buffer = str(buffer or "")
    completed_commands: list[str] = []
    for char in cleaned:
        if char in ("\r", "\n"):
            command = command_buffer.strip()
            command_buffer = ""
            if command:
                completed_commands.append(command)
            continue
        if char in ("\x7f", "\b"):
            command_buffer = command_buffer[:-1]
            continue
        if char == "\x15":
            command_buffer = ""
            continue
        if ord(char) < 32 and char != "\t":
            continue
        command_buffer = (command_buffer + char)[-8000:]
    return TerminalInputCapture(buffer=command_buffer, commands=completed_commands)


def strip_ansi_and_controls(text: str) -> str:
    if not text:
        return ""
    out = re.sub(r"\x1B[@-_][0-?]*[ -/]*[@-~]", "", text)
    return re.sub(r"[\x00-\x08\x0B-\x1F\x7F]", "", out)


def normalize_manual_command_output(command: str, output: str) -> str:
    clean = strip_ansi_and_controls(output or "").replace("\r", "")
    lines = clean.splitlines()
    while lines and not lines[0].strip():
        lines.pop(0)
    if lines:
        first = lines[0].strip()
        if first == command.strip():
            lines.pop(0)
    return "\n".join(lines).strip()[-12000:]
