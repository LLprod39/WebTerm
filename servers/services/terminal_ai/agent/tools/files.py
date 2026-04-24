"""
File manipulation tools for the Terminal Agent (``read_file``,
``edit_file``, ``list_files``).

All tools use a non-PTY SSH channel (``conn.run``) so they do NOT
pollute the interactive shell buffer. Large reads are chunk-limited;
edits take an automatic rollback snapshot (2.4) before touching the
file so the user can revert in one click.

Every tool accepts an optional ``target`` parameter — empty means the
session's primary server, a named handle means an authorised extra
server (see ``list_targets``).
"""

from __future__ import annotations

import asyncio
import base64
import logging
import shlex

from pydantic import BaseModel, ConfigDict, Field

from servers.services.terminal_ai.agent.schemas import ToolResult
from servers.services.terminal_ai.agent.tools.base import (
    ServerTarget,
    ToolContext,
    tool_err,
    tool_ok,
)

logger = logging.getLogger(__name__)

# Per-read caps — larger files force the agent to use `grep`/`head`/`tail`.
MAX_READ_BYTES = 200_000

# Per-edit cap on patch body size.
MAX_PATCH_BYTES = 40_000

# Wall-clock timeouts.
READ_TIMEOUT_SEC = 20.0
EDIT_TIMEOUT_SEC = 20.0
LIST_TIMEOUT_SEC = 15.0


async def _resolve_conn(
    ctx: ToolContext, target_name: str
) -> tuple[ServerTarget | None, object | None, ToolResult | None]:
    """Resolve a named target and ensure an SSH connection is open.

    Returns ``(target, conn, err)``. If either the target is unknown
    or the connection cannot be opened, ``err`` is populated and the
    tool should return it directly.
    """
    target = ctx.resolve_target(target_name)
    if target is None:
        avail = ", ".join(t.name for t in ctx.all_targets()) or "(none)"
        return (
            None,
            None,
            tool_err(
                f"unknown target '{target_name}'; available: {avail}",
                output=(
                    f"Target '{target_name}' is not authorised for this "
                    f"session. Available: {avail}."
                ),
            ),
        )
    conn = await ctx.ensure_connection(target)
    if conn is None:
        return (
            target,
            None,
            tool_err(
                f"SSH connection to '{target.name}' unavailable",
                fatal=target.is_primary,
            ),
        )
    return target, conn, None


# ---------------------------------------------------------------------------
# read_file
# ---------------------------------------------------------------------------


class ReadFileArgs(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    path: str = Field(min_length=1, max_length=1024)
    """Absolute path on the remote server."""

    target: str = Field(default="", max_length=64)
    """Server handle (empty = primary). See `list_targets`."""

    offset: int = Field(default=0, ge=0)
    """Byte offset to start reading from (0 = start of file)."""

    length: int = Field(default=MAX_READ_BYTES, ge=1, le=MAX_READ_BYTES)
    """Maximum bytes to read (capped at MAX_READ_BYTES=200KB)."""


class ReadFileTool:
    """Read a slice of a file from the remote server."""

    name: str = "read_file"
    description: str = (
        "Read up to 200KB of a file on an authorised server without "
        "polluting the interactive shell. Use for config inspection, "
        "log snippets, or verifying an earlier edit. For larger files, "
        "use `grep` or chain `shell` with `tail`/`head`. Returns the "
        "file content plus its size and mtime."
    )
    args_schema: type[BaseModel] = ReadFileArgs

    async def run(self, args: ReadFileArgs, ctx: ToolContext) -> ToolResult:
        target, conn, err = await _resolve_conn(ctx, args.target)
        if err is not None:
            return err

        path = args.path.strip()
        if not path:
            return tool_err("empty path")

        q_path = shlex.quote(path)
        # Combined stat + dd call to fetch metadata + bytes in one round-trip.
        # base64 on the content keeps binary safe; we decode client-side.
        stat_cmd = (
            f"stat -c '%s %Y' {q_path} 2>/dev/null || echo 'MISSING MISSING'"
        )
        dd_cmd = (
            f"dd if={q_path} bs=1 skip={args.offset} count={args.length} "
            "2>/dev/null | base64 -w0"
        )
        full_cmd = f"printf 'STAT:'; {stat_cmd}; printf '\\nDATA:'; {dd_cmd}"

        try:
            result = await asyncio.wait_for(
                conn.run(full_cmd, check=False),
                timeout=READ_TIMEOUT_SEC,
            )
        except asyncio.TimeoutError:
            return tool_err(f"read_file timeout ({READ_TIMEOUT_SEC}s)")
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            return tool_err(f"{type(exc).__name__}: {exc}")

        raw = str(getattr(result, "stdout", "") or "")
        try:
            stat_line = raw.split("STAT:", 1)[1].split("\nDATA:", 1)[0].strip()
            data_b64 = raw.split("\nDATA:", 1)[1].strip()
        except Exception:
            return tool_err("failed to parse read_file output")

        if stat_line.startswith("MISSING"):
            return tool_err(
                f"file not found: {path}",
                output=f"File does not exist on {target.name}: {path}",
            )

        try:
            size_str, mtime_str = stat_line.split()
            size_bytes = int(size_str)
            mtime_epoch = int(mtime_str)
        except Exception:
            size_bytes = -1
            mtime_epoch = 0

        try:
            content_bytes = base64.b64decode(data_b64)
            # Decode as utf-8, replacing invalid bytes so the LLM gets
            # something useful even for binary files.
            content = content_bytes.decode("utf-8", errors="replace")
        except Exception as exc:
            return tool_err(f"base64 decode failed: {exc}")

        header = (
            f"Path: {path}\nTarget: {target.name}\nSize: {size_bytes} bytes"
            f"\nMTime: {mtime_epoch}\n--- content ---\n"
        )
        return tool_ok(
            header + content,
            data={
                "path": path,
                "target": target.name,
                "size": size_bytes,
                "mtime": mtime_epoch,
                "bytes_returned": len(content_bytes),
            },
        )


# ---------------------------------------------------------------------------
# edit_file (write full contents; snapshot taken first)
# ---------------------------------------------------------------------------


class EditFileArgs(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    path: str = Field(min_length=1, max_length=1024)
    """Absolute path on the remote server to write."""

    content: str = Field(max_length=MAX_PATCH_BYTES)
    """Full new file contents (the file is overwritten atomically)."""

    target: str = Field(default="", max_length=64)
    """Server handle (empty = primary)."""

    create: bool = Field(default=False)
    """If True, allow creating the file when it does not yet exist.
    Otherwise missing files cause an error (so the agent cannot
    accidentally birth new configs)."""


class EditFileTool:
    """Overwrite a file atomically, taking a rollback snapshot first."""

    name: str = "edit_file"
    description: str = (
        "Overwrite a file on an authorised server with new contents. "
        "A pre-edit snapshot is captured automatically so the change "
        "can be rolled back in one click via the UI. Content must be "
        "≤40KB. By default the file must already exist (set `create=true` "
        "to permit creating new files). Writes go to a temp file and "
        "are renamed atomically to avoid partial writes."
    )
    args_schema: type[BaseModel] = EditFileArgs

    async def run(self, args: EditFileArgs, ctx: ToolContext) -> ToolResult:
        target, conn, err = await _resolve_conn(ctx, args.target)
        if err is not None:
            return err

        path = args.path.strip()
        if not path:
            return tool_err("empty path")

        if target.read_only:
            return tool_err(
                f"target '{target.name}' is read-only; edit_file refused",
                output=(
                    f"Server '{target.display_name or target.name}' is in "
                    "read-only mode."
                ),
            )

        if ctx.dry_run:
            return tool_ok(
                f"[DRY-RUN on {target.name}] Would write {len(args.content)} bytes to {path}",
                data={
                    "path": path,
                    "target": target.name,
                    "bytes": len(args.content),
                    "dry_run": True,
                },
            )

        q_path = shlex.quote(path)

        # Check existence + capture snapshot if file exists.
        snapshot_saved = False
        snapshot_id: int | None = None
        try:
            exists_res = await asyncio.wait_for(
                conn.run(f"test -f {q_path} && echo EXISTS || echo MISSING"),
                timeout=5.0,
            )
            exists_out = str(getattr(exists_res, "stdout", "")).strip()
        except Exception as exc:
            return tool_err(f"existence check failed: {exc}")

        file_existed = exists_out == "EXISTS"
        if not file_existed and not args.create:
            return tool_err(
                f"file not found: {path} (pass create=true to create)",
                output=(
                    f"'{path}' does not exist on {target.name}. Pass "
                    "create=true if you really want to create it."
                ),
            )

        if file_existed:
            try:
                cat_res = await asyncio.wait_for(
                    conn.run(f"cat {q_path}"), timeout=10.0
                )
                original = str(getattr(cat_res, "stdout", "") or "")
                if ctx.user_id is not None and target.server_id and original:
                    from asgiref.sync import sync_to_async

                    from servers.services.snapshot_service import save_snapshot

                    snap_pk = await sync_to_async(save_snapshot)(
                        server_id=target.server_id,
                        user_id=ctx.user_id,
                        command=f"agent.edit_file:{path}",
                        file_path=path,
                        content=original,
                    )
                    snapshot_id = int(snap_pk) if snap_pk else None
                    snapshot_saved = bool(snapshot_id)
            except Exception as exc:  # noqa: BLE001 — snapshot best-effort
                logger.warning("agent edit_file snapshot failed: %s", exc)

        # Atomic write: encode content as base64 → decode remotely into a
        # temp file → mv over the target path.
        b64 = base64.b64encode(args.content.encode("utf-8")).decode("ascii")
        tmp_path = f"{path}.weuagent-{asyncio.get_running_loop().time():.0f}.tmp"
        q_tmp = shlex.quote(tmp_path)
        write_cmd = (
            f"printf %s {shlex.quote(b64)} | base64 -d > {q_tmp} "
            f"&& mv {q_tmp} {q_path}"
        )
        try:
            res = await asyncio.wait_for(
                conn.run(write_cmd, check=False), timeout=EDIT_TIMEOUT_SEC
            )
        except asyncio.TimeoutError:
            return tool_err(f"edit_file timeout ({EDIT_TIMEOUT_SEC}s)")
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            return tool_err(f"{type(exc).__name__}: {exc}")

        exit_raw = getattr(res, "exit_status", None)
        exit_code = int(exit_raw) if exit_raw is not None else 1
        if exit_code != 0:
            stderr = str(getattr(res, "stderr", "") or "")[:500]
            return tool_err(
                f"write failed (exit {exit_code}): {stderr}",
                output=f"Write failed on {target.name}: {stderr}",
            )

        summary = (
            f"Wrote {len(args.content)} bytes to {path} on {target.name}."
        )
        if snapshot_saved:
            summary += f" Rollback snapshot #{snapshot_id} saved."
        elif file_existed:
            summary += " (snapshot skipped — check logs)"
        else:
            summary += " (new file)"

        return tool_ok(
            summary,
            data={
                "path": path,
                "target": target.name,
                "bytes": len(args.content),
                "snapshot_id": snapshot_id,
                "created": not file_existed,
            },
        )


# ---------------------------------------------------------------------------
# list_files
# ---------------------------------------------------------------------------


class ListFilesArgs(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    path: str = Field(default=".", max_length=1024)
    """Directory to list."""

    target: str = Field(default="", max_length=64)
    all_files: bool = Field(default=False)
    """Include hidden files (like ``ls -a``)."""


class ListFilesTool:
    """List files in a directory with structured metadata."""

    name: str = "list_files"
    description: str = (
        "List entries in a directory on an authorised server with "
        "size + mtime metadata. Equivalent to `ls -la --time-style=+%s` "
        "but parsed into structured JSON for the agent."
    )
    args_schema: type[BaseModel] = ListFilesArgs

    async def run(self, args: ListFilesArgs, ctx: ToolContext) -> ToolResult:
        target, conn, err = await _resolve_conn(ctx, args.target)
        if err is not None:
            return err

        path = args.path.strip() or "."
        q_path = shlex.quote(path)
        flags = "-la" if args.all_files else "-l"
        cmd = f"ls {flags} --time-style=+%s {q_path} 2>&1"

        try:
            res = await asyncio.wait_for(
                conn.run(cmd, check=False), timeout=LIST_TIMEOUT_SEC
            )
        except asyncio.TimeoutError:
            return tool_err(f"list_files timeout ({LIST_TIMEOUT_SEC}s)")
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            return tool_err(f"{type(exc).__name__}: {exc}")

        exit_raw = getattr(res, "exit_status", None)
        exit_code = int(exit_raw) if exit_raw is not None else 1
        raw = str(getattr(res, "stdout", "") or "")
        if exit_code != 0:
            return tool_err(
                f"ls exited {exit_code}: {raw[:300]}",
                output=f"Cannot list {path} on {target.name}: {raw[:300]}",
            )

        entries: list[dict] = []
        for line in raw.splitlines():
            parts = line.split(None, 6)
            if len(parts) < 7 or not parts[0].startswith(("-", "d", "l")):
                continue
            perm, _nlink, user, group, size, mtime, name = parts
            try:
                entries.append(
                    {
                        "name": name,
                        "type": (
                            "dir"
                            if perm.startswith("d")
                            else "link"
                            if perm.startswith("l")
                            else "file"
                        ),
                        "perm": perm,
                        "size": int(size),
                        "mtime": int(mtime),
                        "owner": user,
                        "group": group,
                    }
                )
            except ValueError:
                continue

        summary = (
            f"Directory: {path} on {target.name}\n"
            f"Entries: {len(entries)}"
        )
        return tool_ok(
            summary
            + "\n"
            + "\n".join(
                f"  {e['type']:4s} {e['perm']} {e['size']:>10d} {e['name']}"
                for e in entries[:100]
            ),
            data={"path": path, "target": target.name, "entries": entries},
        )


__all__ = [
    "ReadFileTool",
    "ReadFileArgs",
    "EditFileTool",
    "EditFileArgs",
    "ListFilesTool",
    "ListFilesArgs",
]
