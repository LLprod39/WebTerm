"""
Rollback snapshot service (2.4).

Detects file-modifying commands, captures pre-execution snapshots via SSH,
and generates restore commands.  Pure business logic — no WebSocket or
consumer dependencies.

Public API
----------
- ``detect_target_file(cmd) -> str | None``
- ``save_snapshot(server_id, user_id, cmd, file_path, content) -> int``
- ``list_snapshots(server_id, *, user_id=None, limit=20) -> list[dict]``
- ``build_restore_command(snapshot_id) -> str | None``
"""

from __future__ import annotations

import hashlib
import re

# ---------------------------------------------------------------------------
# File-modification detection patterns
# ---------------------------------------------------------------------------

# Each entry: (label, compiled regex, group name that captures the file path)
# The regex MUST have a named group ``(?P<path>...)`` for the target file.

_ABS_PATH = r"(?P<path>/[^\s;|&><\"']+)"

_FILE_MOD_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    # sed -i[.bak] ... /path
    (
        "sed_inplace",
        re.compile(
            r"\bsed\s+"
            r"(?:-[a-zA-Z]*i[a-zA-Z]*(?:\.[a-zA-Z0-9]+)?\s+)"
            r"(?:(?:'[^']*'|\"[^\"]*\"|[^\s]+)\s+)"
            + _ABS_PATH,
            re.IGNORECASE,
        ),
    ),
    # echo/printf ... > /path  (single redirect, overwrite)
    (
        "redirect_overwrite",
        re.compile(r"[^>]>\s*" + _ABS_PATH),
    ),
    # echo/printf ... >> /path  (append)
    (
        "redirect_append",
        re.compile(r">>\s*" + _ABS_PATH),
    ),
    # tee [-a] /path
    (
        "tee_write",
        re.compile(r"\btee\s+(?:-[a-zA-Z]+\s+)*" + _ABS_PATH, re.IGNORECASE),
    ),
    # cp ... /dest  (last arg is dest; only if absolute)
    (
        "cp_overwrite",
        re.compile(
            r"\bcp\s+(?:-[a-zA-Z]+\s+)*\S+\s+" + _ABS_PATH + r"\s*$",
            re.IGNORECASE,
        ),
    ),
    # mv ... /dest
    (
        "mv_overwrite",
        re.compile(
            r"\bmv\s+(?:-[a-zA-Z]+\s+)*\S+\s+" + _ABS_PATH + r"\s*$",
            re.IGNORECASE,
        ),
    ),
]

# Maximum file size we'll snapshot (bytes).  Larger files are skipped to
# avoid blowing up the DB and SSH channel.
MAX_SNAPSHOT_BYTES = 512 * 1024  # 512 KB


def detect_target_file(cmd: str) -> str | None:
    """Return the absolute file path that *cmd* will modify, or ``None``.

    Only absolute paths (starting with ``/``) are detected — relative paths
    are ambiguous without CWD context and are intentionally skipped.
    """
    if not cmd:
        return None
    text = str(cmd).strip()
    for _label, pattern in _FILE_MOD_PATTERNS:
        m = pattern.search(text)
        if m:
            path = m.group("path").rstrip(";").rstrip()
            if path.startswith("/") and len(path) > 1:
                return path
    return None


# ---------------------------------------------------------------------------
# DB operations
# ---------------------------------------------------------------------------


def save_snapshot(
    server_id: int,
    user_id: int,
    command: str,
    file_path: str,
    content: str,
) -> int:
    """Persist a snapshot and return its PK.

    Computes SHA-256 hash for dedup/integrity.  If the previous snapshot
    for the same server+file has the same hash, skip the duplicate.
    """
    from servers.models import CommandSnapshot

    content_str = str(content or "")
    h = hashlib.sha256(content_str.encode("utf-8", errors="replace")).hexdigest()
    byte_size = len(content_str.encode("utf-8", errors="replace"))

    # Dedup: skip if last snapshot for this file on this server is identical.
    last = (
        CommandSnapshot.objects.filter(server_id=server_id, file_path=file_path)
        .order_by("-created_at")
        .values_list("content_hash", flat=True)
        .first()
    )
    if last == h:
        return 0  # no-op, content unchanged

    snap = CommandSnapshot.objects.create(
        server_id=server_id,
        user_id=user_id,
        command=command[:2000],
        file_path=file_path[:1024],
        content=content_str,
        content_hash=h,
        byte_size=byte_size,
    )
    return snap.pk


def list_snapshots(
    server_id: int,
    *,
    user_id: int | None = None,
    limit: int = 30,
) -> list[dict]:
    """Return recent snapshots for *server_id* as plain dicts."""
    from servers.models import CommandSnapshot

    qs = CommandSnapshot.objects.filter(server_id=server_id)
    if user_id:
        qs = qs.filter(user_id=user_id)
    rows = qs.order_by("-created_at")[:limit]
    return [
        {
            "id": r.pk,
            "file_path": r.file_path,
            "command": r.command,
            "byte_size": r.byte_size,
            "content_hash": r.content_hash,
            "created_at": r.created_at.isoformat(),
            "restored_at": r.restored_at.isoformat() if r.restored_at else None,
        }
        for r in rows
    ]


def get_snapshot_detail(snapshot_id: int) -> dict | None:
    """Return full snapshot including content, or ``None``."""
    from servers.models import CommandSnapshot

    try:
        r = CommandSnapshot.objects.get(pk=snapshot_id)
    except CommandSnapshot.DoesNotExist:
        return None
    return {
        "id": r.pk,
        "server_id": r.server_id,
        "user_id": r.user_id,
        "file_path": r.file_path,
        "command": r.command,
        "content": r.content,
        "byte_size": r.byte_size,
        "content_hash": r.content_hash,
        "created_at": r.created_at.isoformat(),
        "restored_at": r.restored_at.isoformat() if r.restored_at else None,
    }


def build_restore_command(snapshot_id: int) -> str | None:
    """Generate a shell command that restores the file from *snapshot_id*.

    Uses a heredoc so the content is self-contained. Returns ``None`` if
    the snapshot does not exist or content is empty.
    """
    from servers.models import CommandSnapshot

    try:
        snap = CommandSnapshot.objects.get(pk=snapshot_id)
    except CommandSnapshot.DoesNotExist:
        return None
    if not snap.content and not snap.file_path:
        return None

    # Mark as restored
    from django.utils import timezone

    CommandSnapshot.objects.filter(pk=snapshot_id).update(restored_at=timezone.now())

    # Empty content → file didn't exist before; restore = remove
    if not snap.content:
        return f"rm -f {_shell_quote(snap.file_path)}"

    # Use heredoc with a unique delimiter
    delimiter = "_WEUAI_RESTORE_EOF_"
    return (
        f"cat > {_shell_quote(snap.file_path)} << '{delimiter}'\n"
        f"{snap.content}\n"
        f"{delimiter}"
    )


def _shell_quote(path: str) -> str:
    """Minimal quoting for safe shell embedding of a file path."""
    if not path:
        return "''"
    # If path contains no special chars, return as-is
    if re.match(r"^[a-zA-Z0-9_./-]+$", path):
        return path
    return "'" + path.replace("'", "'\\''") + "'"
