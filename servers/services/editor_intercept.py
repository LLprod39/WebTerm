"""
Service for detecting terminal editor commands (nano, vim, vi, etc.)
and extracting the file path so the frontend can open a GUI editor instead.
"""

from __future__ import annotations

import re

# Editors we intercept. Order matters for regex alternation.
_EDITORS = ("nano", "vim", "vi", "mcedit", "joe", "pico", "sudoedit")
_EDITOR_RE = re.compile(
    r"^(?:sudo\s+)?(?:" + "|".join(re.escape(e) for e in _EDITORS) + r")"
    r"\s+"
    r"(?:(?:-\S+)\s+)*"   # skip flags like -w, --line=5
    r"([^\s;|&]+)",        # capture first positional arg (the file path)
    re.IGNORECASE,
)

# Interactive full-screen / TUI commands that take over the pty and read stdin
# directly. Injecting the exit-code marker into the pty after such a command
# would corrupt its state, because the marker bytes are delivered to the TUI
# program as keystrokes (not to the parent shell). See `_should_use_manual_command_marker`.
_INTERACTIVE_TUI_NAMES = _EDITORS + (
    "emacs",
    "less",
    "more",
    "most",
    "man",
    "top",
    "htop",
    "btop",
    "atop",
    "nmon",
    "iotop",
    "iftop",
    "nethogs",
    "watch",
    "tmux",
    "screen",
    "dialog",
    "whiptail",
)
_INTERACTIVE_TUI_RE = re.compile(
    r"^(?:sudo\s+)?(?:" + "|".join(re.escape(e) for e in _INTERACTIVE_TUI_NAMES) + r")(?:\s|$)",
    re.IGNORECASE,
)


def detect_editor_command(raw_command: str) -> dict | None:
    """
    Parse a shell command and detect if it invokes a text editor.

    Returns ``{"editor": "nano", "path": "/etc/hosts", "sudo": True}``
    or ``None`` if this is not an editor invocation.
    """
    stripped = raw_command.strip()
    if not stripped:
        return None

    m = _EDITOR_RE.match(stripped)
    if not m:
        return None

    path = m.group(1)
    # Sanity: must look like a file path (not a flag)
    if path.startswith("-"):
        return None

    sudo = stripped.lower().startswith("sudo")
    # Extract the editor name
    after_sudo = stripped.split(None, 1)[0].lower() if not sudo else (stripped.split(None, 2)[1].lower() if len(stripped.split()) > 1 else "")
    editor = after_sudo if after_sudo in _EDITORS else "unknown"

    return {"editor": editor, "path": path, "sudo": sudo}


def is_interactive_tui_command(raw_command: str) -> bool:
    """
    Return True if the command invokes an interactive full-screen TUI program
    (editor, pager, system monitor, multiplexer, …) that takes over the pty.

    Such commands must NOT be wrapped with exit-code markers — otherwise the
    marker bytes are delivered to the running program as keystrokes (instead
    of the shell), which corrupts its UI and leaves the terminal "frozen"
    (the user's keystrokes and Ctrl+X stop behaving correctly).
    """
    stripped = (raw_command or "").strip()
    if not stripped:
        return False
    return bool(_INTERACTIVE_TUI_RE.match(stripped))
