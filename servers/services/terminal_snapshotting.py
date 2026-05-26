"""
Pre-execution file snapshot capture for terminal AI commands.

Best-effort service: detects file-modifying commands, reads the target file via
SSH, and persists a snapshot without blocking command execution on failures.
"""

from __future__ import annotations

import asyncio

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
    if not file_path or not ssh_conn:
        return False
    try:
        result = await asyncio.wait_for(
            ssh_conn.run(
                f"cat {file_path} 2>/dev/null",
                check=False,
            ),
            timeout=timeout_seconds,
        )
        content = str(result.stdout or "")
        if len(content.encode("utf-8", errors="replace")) > MAX_SNAPSHOT_BYTES:
            logger.debug(
                "Snapshot skipped: file %s too large (%d bytes)",
                file_path,
                len(content),
            )
            return False
        await sync_to_async(save_snapshot)(
            server_id=server_id,
            user_id=user_id,
            command=command,
            file_path=file_path,
            content=content,
        )
        logger.debug("Snapshot saved for %s before cmd_id=%s", file_path, cmd_id)
        return True
    except Exception as exc:
        logger.debug("Snapshot capture failed for %s: %s", file_path, exc)
        return False
