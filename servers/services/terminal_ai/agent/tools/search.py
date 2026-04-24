"""
Structured search tool (``grep``) for the Terminal Agent.

Wraps POSIX ``grep -rn`` on the remote server and parses its output into
``(path, line, text)`` triples so the agent gets actionable structured
data instead of raw stdout. Results are capped to prevent context
explosion on giant codebases or log directories.
"""

from __future__ import annotations

import asyncio
import logging
import shlex

from pydantic import BaseModel, ConfigDict, Field

from servers.services.terminal_ai.agent.schemas import ToolResult
from servers.services.terminal_ai.agent.tools.base import (
    ToolContext,
    tool_err,
    tool_ok,
)
from servers.services.terminal_ai.agent.tools.files import _resolve_conn

logger = logging.getLogger(__name__)

GREP_TIMEOUT_SEC = 30.0
MAX_MATCHES = 200
MAX_MATCH_LEN = 400


class GrepArgs(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    pattern: str = Field(min_length=1, max_length=512)
    """Fixed string or regex (see ``regex`` flag) to search for."""

    path: str = Field(default=".", max_length=1024)
    """Directory or file to search in."""

    target: str = Field(default="", max_length=64)
    """Server handle (empty = primary)."""

    regex: bool = Field(default=False)
    """If True, treat pattern as extended regex (``grep -E``).
    Default is fixed-string for safety (``grep -F``)."""

    case_insensitive: bool = Field(default=False)

    include: str = Field(default="", max_length=256)
    """Glob like ``*.py`` to limit matched files (``grep --include=``)."""

    max_matches: int = Field(default=MAX_MATCHES, ge=1, le=MAX_MATCHES)


class GrepTool:
    """Search for a pattern across files on the remote server."""

    name: str = "grep"
    description: str = (
        "Recursively search for a pattern across files on an authorised "
        "server. Results are parsed into `(path, line, text)` entries "
        "(capped at 200 matches). Defaults to fixed-string matching; "
        "set `regex=true` to use extended regex. Use `include` with a "
        "glob (e.g. `*.conf`) to narrow scope."
    )
    args_schema: type[BaseModel] = GrepArgs

    async def run(self, args: GrepArgs, ctx: ToolContext) -> ToolResult:
        target, conn, err = await _resolve_conn(ctx, args.target)
        if err is not None:
            return err

        pattern = args.pattern.strip()
        if not pattern:
            return tool_err("empty pattern")

        flags = ["-rn"]
        if args.regex:
            flags.append("-E")
        else:
            flags.append("-F")
        if args.case_insensitive:
            flags.append("-i")
        if args.include:
            flags.append(f"--include={shlex.quote(args.include)}")

        # Limit output server-side to avoid huge transfers.
        max_out = int(args.max_matches) * (MAX_MATCH_LEN + 100)
        flag_str = " ".join(flags)
        cmd = (
            f"grep {flag_str} -- {shlex.quote(pattern)} "
            f"{shlex.quote(args.path)} 2>/dev/null | head -c {max_out}"
        )

        try:
            res = await asyncio.wait_for(
                conn.run(cmd, check=False), timeout=GREP_TIMEOUT_SEC
            )
        except asyncio.TimeoutError:
            return tool_err(f"grep timeout ({GREP_TIMEOUT_SEC}s)")
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            return tool_err(f"{type(exc).__name__}: {exc}")

        raw = str(getattr(res, "stdout", "") or "")
        exit_raw = getattr(res, "exit_status", None)
        exit_code = int(exit_raw) if exit_raw is not None else 1

        # grep exits 1 when no matches → treat as ok-empty.
        if exit_code not in (0, 1):
            return tool_err(
                f"grep exit {exit_code}",
                output=f"grep failed on {target.name}: exit {exit_code}",
            )

        matches: list[dict] = []
        for line in raw.splitlines()[: args.max_matches]:
            # ``grep -rn`` format: path:line:text
            parts = line.split(":", 2)
            if len(parts) < 3:
                continue
            path, ln_str, text = parts
            try:
                ln = int(ln_str)
            except ValueError:
                continue
            if len(text) > MAX_MATCH_LEN:
                text = text[:MAX_MATCH_LEN] + "…"
            matches.append({"path": path, "line": ln, "text": text})

        if not matches:
            return tool_ok(
                f"No matches for {pattern!r} in {args.path} on {target.name}.",
                data={
                    "pattern": pattern,
                    "target": target.name,
                    "matches": [],
                },
            )

        summary = (
            f"Matches for {pattern!r} in {args.path} on {target.name}: "
            f"{len(matches)}{' (capped)' if len(matches) == args.max_matches else ''}"
        )
        body = "\n".join(
            f"  {m['path']}:{m['line']}: {m['text']}" for m in matches
        )
        return tool_ok(
            summary + "\n" + body,
            data={
                "pattern": pattern,
                "target": target.name,
                "matches": matches,
                "truncated": len(matches) == args.max_matches,
            },
        )


__all__ = ["GrepTool", "GrepArgs"]
