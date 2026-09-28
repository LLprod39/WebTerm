"""Windows OpenSSH session helpers for the interactive terminal.

Linux sessions keep bash exports and LF. Windows sessions talk to ConPTY:
UTF-8 bootstrap, PowerShell environment assignments, CR for Enter, and
non-zero pixel sizes so window-change reaches the console host.
"""

from __future__ import annotations

import re
from typing import Any

from servers.services.terminal_input import TerminalSize, build_shell_exports

OS_TYPE_LINUX = "linux"
OS_TYPE_WINDOWS = "windows"
WINDOWS_CELL_PX_WIDTH = 8
WINDOWS_CELL_PX_HEIGHT = 16

# ASCII only: the console code page may still be OEM when this line is typed.
WINDOWS_UTF8_BOOTSTRAP = (
    "chcp 65001 > $null; "
    "[Console]::InputEncoding = New-Object System.Text.UTF8Encoding $false; "
    "[Console]::OutputEncoding = [Console]::InputEncoding"
)

_ENV_KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def normalize_os_type(value: object, *, default: str = OS_TYPE_LINUX) -> str:
    raw = str(value if value is not None else default).strip().lower() or default
    if raw not in {OS_TYPE_LINUX, OS_TYPE_WINDOWS}:
        raise ValueError("Invalid os_type")
    return raw


def host_os_type(server: Any) -> str:
    raw = getattr(server, "os_type", None)
    if callable(raw):
        raw = raw()
    try:
        return normalize_os_type(raw or OS_TYPE_LINUX)
    except ValueError:
        return OS_TYPE_LINUX


def is_windows_host(server: Any) -> bool:
    if hasattr(server, "is_windows") and callable(server.is_windows):
        return bool(server.is_windows())
    return host_os_type(server) == OS_TYPE_WINDOWS


def windows_terminal_pixels(term_size: TerminalSize) -> tuple[int, int]:
    if term_size.cols <= 0 or term_size.rows <= 0:
        return (0, 0)
    return (term_size.cols * WINDOWS_CELL_PX_WIDTH, term_size.rows * WINDOWS_CELL_PX_HEIGHT)


def normalize_windows_pty_input(data: str) -> str:
    """Turn a lone LF into CR. Leave CR and CRLF untouched."""
    if not data or "\n" not in data:
        return data
    parts: list[str] = []
    index = 0
    while index < len(data):
        if data.startswith("\r\n", index):
            parts.append("\r\n")
            index += 2
            continue
        char = data[index]
        parts.append("\r" if char == "\n" else char)
        index += 1
    return "".join(parts)


def _clean_env_value(value: object) -> str:
    return str(value if value is not None else "").replace("\n", " ").replace("\r", " ").strip()


def build_powershell_env_assignments(env_vars: dict[str, Any] | None) -> str:
    assignments: list[str] = []
    for key_raw, value_raw in (env_vars or {}).items():
        key = str(key_raw or "").strip()
        if not key or not _ENV_KEY_RE.match(key):
            continue
        value = _clean_env_value(value_raw).replace("'", "''")
        assignments.append(f"$env:{key} = '{value}'")
    return "; ".join(assignments)


def build_session_prelude(server: Any, env_vars: dict[str, Any] | None) -> str:
    """Text written to the PTY once, right after it opens. Empty when nothing to send."""
    if is_windows_host(server):
        chunks = [WINDOWS_UTF8_BOOTSTRAP]
        env_line = build_powershell_env_assignments(env_vars)
        if env_line:
            chunks.append(env_line)
        return "; ".join(chunks) + "\r"
    exports = build_shell_exports(env_vars or {})
    if not exports:
        return ""
    return exports + "\n"
