"""State helpers for SSH terminal stream handling."""

from __future__ import annotations

import contextlib
import re
from collections.abc import MutableMapping

from servers.services import terminal_input


def filter_internal_markers(
    *,
    stream: str,
    data: str,
    marker_prefix: str,
    marker_suppress: MutableMapping[str, bool],
    marker_line_buf: MutableMapping[str, str],
) -> tuple[str, list[tuple[int, int]]]:
    """
    Hide internal marker lines used to capture exit codes from terminal output.

    The caller owns ``marker_suppress`` and ``marker_line_buf`` because marker
    lines can span multiple SSH chunks.
    """
    if not data:
        return "", []

    marker_suppress.setdefault("stdout", False)
    marker_suppress.setdefault("stderr", False)
    marker_line_buf.setdefault("stdout", "")
    marker_line_buf.setdefault("stderr", "")

    markers: list[tuple[int, int]] = []
    out: list[str] = []
    i = 0
    suppress = bool(marker_suppress.get(stream, False))
    buf = marker_line_buf.get(stream, "")
    marker_re = re.compile(rf"^{re.escape(marker_prefix)}(\d+):(-?\d+)__\s*$")

    while i < len(data):
        if suppress:
            nl = data.find("\n", i)
            if nl == -1:
                buf += data[i:]
                i = len(data)
                break
            buf += data[i:nl]
            match = marker_re.match(buf.strip())
            if match:
                with contextlib.suppress(Exception):
                    markers.append((int(match.group(1)), int(match.group(2))))
            buf = ""
            suppress = False
            out.append("\n")
            i = nl + 1
            continue

        idx = data.find(marker_prefix, i)
        if idx == -1:
            out.append(data[i:])
            i = len(data)
            break

        out.append(data[i:idx])
        suppress = True
        buf = ""
        i = idx

    marker_suppress[stream] = suppress
    marker_line_buf[stream] = buf
    return "".join(out), markers


def set_exit_future_result(
    exit_futures: MutableMapping[int, object] | None,
    cmd_id: int,
    exit_code: int,
) -> None:
    """Resolve an AI command exit future if the marker belongs to one."""
    try:
        future = (exit_futures or {}).get(int(cmd_id))
        if future and not future.done():
            future.set_result(int(exit_code))
    except Exception:
        return


def append_clean_output(current: str | None, text: str, *, limit: int) -> str:
    """Append sanitized terminal text and keep only the most recent chars."""
    if not text:
        return current or ""
    clean = terminal_input.strip_ansi_and_controls(text)
    if not clean:
        return current or ""
    value = (current or "") + clean
    if len(value) > limit:
        return value[-limit:]
    return value
