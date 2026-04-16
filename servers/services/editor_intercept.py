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
