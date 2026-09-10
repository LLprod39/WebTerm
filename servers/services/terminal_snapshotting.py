"""
Pre-execution file snapshot capture for terminal AI commands.

Best-effort service: detects file-modifying commands, reads the target file via
SSH, and persists a snapshot without blocking command execution on failures.
"""

from __future__ import annotations

import asyncio
import stat

import asyncssh
from asgiref.sync import sync_to_async
from loguru import logger


async def capture_pre_execution_snapshot(
    *,
    command: str,
    cmd_id: int,
    ssh_conn,
    server_id: int,
    user_id: int | None,
    timeout_seconds: float = 10.0,
) -> bool:
    from servers.services.snapshot_service import (
        MAX_SNAPSHOT_BYTES,
        detect_target_file,
        save_snapshot,
    )

    file_path = detect_target_file(command)
    if not file_path or not ssh_conn or not user_id:
        return False

    async def read_file():
        async with ssh_conn.start_sftp_client() as sftp:
            try:
                attrs = await sftp.lstat(file_path)
            except asyncssh.SFTPNoSuchFile:
                return "", False
            # Do not mistake directories, symlinks, unreadable files or binary
            # content for absent files. Read a bounded amount even if it grows.
            if attrs.permissions is None or not stat.S_ISREG(attrs.permissions):
                return None
            if attrs.size is not None and attrs.size > MAX_SNAPSHOT_BYTES:
                return None
            async with sftp.open(file_path, "rb") as remote:
                content_bytes = await remote.read(MAX_SNAPSHOT_BYTES + 1)
            if len(content_bytes) > MAX_SNAPSHOT_BYTES:
                return None
            return content_bytes.decode("utf-8"), True

    try:
        captured = await asyncio.wait_for(read_file(), timeout=timeout_seconds)
        if captured is None:
            return False
        content, file_existed = captured
        await sync_to_async(save_snapshot)(
            server_id=server_id,
            user_id=user_id,
            command=command,
            file_path=file_path,
            content=content,
            file_existed=file_existed,
        )
        logger.debug("Snapshot saved for %s before cmd_id=%s", file_path, cmd_id)
        return True
    except Exception as exc:
        logger.debug("Snapshot capture failed for %s: %s", file_path, exc)
        return False
