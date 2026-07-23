from __future__ import annotations

import asyncio
import subprocess
from collections.abc import Mapping, Sequence


def _decode_output(value: bytes | str | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def _run_process_capture_sync(
    command: Sequence[str],
    *,
    cwd: str,
    env: Mapping[str, str] | None,
    stdin_text: str,
    timeout_seconds: int,
) -> tuple[int, str, str]:
    completed = subprocess.run(
        list(command),
        cwd=cwd,
        env=dict(env) if env is not None else None,
        input=stdin_text,
        text=True,
        capture_output=True,
        timeout=timeout_seconds,
        check=False,
    )
    return int(completed.returncode), completed.stdout or "", completed.stderr or ""


async def run_process_capture(
    command: Sequence[str],
    *,
    cwd: str,
    env: Mapping[str, str] | None = None,
    stdin_text: str = "",
    timeout_seconds: int,
) -> tuple[int, str, str]:
    """Run a subprocess and capture output, with a Windows Selector-loop fallback."""
    try:
        process = await asyncio.create_subprocess_exec(
            *command,
            cwd=cwd,
            env=dict(env) if env is not None else None,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except NotImplementedError:
        return await asyncio.to_thread(
            _run_process_capture_sync,
            command,
            cwd=cwd,
            env=env,
            stdin_text=stdin_text,
            timeout_seconds=timeout_seconds,
        )

    try:
        stdout_bytes, stderr_bytes = await asyncio.wait_for(
            process.communicate(stdin_text.encode("utf-8")),
            timeout=timeout_seconds,
        )
    except TimeoutError as exc:
        process.kill()
        await process.wait()
        raise subprocess.TimeoutExpired(command, timeout_seconds) from exc

    return int(process.returncode or 0), _decode_output(stdout_bytes), _decode_output(stderr_bytes)
