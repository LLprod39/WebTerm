"""Hidden second PTY for Nova on the same SSH connection.

Nova must not type into the operator's xterm. It keeps cwd/env/history on a
separate interactive process created with ``conn.create_process()``. Stdout
never goes to the human terminal.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from servers.services.terminal_ssh_lifecycle import close_ssh_handle
from servers.services.terminal_stream_state import append_clean_output, filter_internal_markers

logger = logging.getLogger(__name__)

NOVA_PTY_MARKER_PREFIX = "__NOVA_PTY_EXIT_"
OUTPUT_LIMIT = 8000
DEFAULT_TIMEOUT_SEC = 30.0


class HiddenPtySession:
    """One hidden shell on an already-open SSH connection."""

    def __init__(self) -> None:
        self.proc: Any = None
        self.output: str = ""
        self.cwd: str = ""
        self.next_id: int = 1
        self._reader_tasks: list[asyncio.Task[Any]] = []
        self._marker_suppress: dict[str, bool] = {"stdout": False, "stderr": False}
        self._marker_line_buf: dict[str, str] = {"stdout": "", "stderr": ""}
        self._exit_futures: dict[int, asyncio.Future[int]] = {}
        self._lock = asyncio.Lock()

    @property
    def attached(self) -> bool:
        return self.proc is not None

    async def attach(
        self,
        conn: Any,
        *,
        term_type: str = "xterm-256color",
        cols: int = 80,
        rows: int = 24,
    ) -> None:
        if self.proc is not None:
            return
        if conn is None:
            raise RuntimeError("SSH connection required for Nova hidden PTY")
        self.proc = await conn.create_process(
            term_type=term_type,
            term_size=(cols, rows, 0, 0),
            encoding="utf-8",
            errors="replace",
        )
        self._reader_tasks = []
        stdout = getattr(self.proc, "stdout", None)
        stderr = getattr(self.proc, "stderr", None)
        if stdout is not None:
            self._reader_tasks.append(asyncio.create_task(self._read_stream(stdout, "stdout")))
        if stderr is not None:
            self._reader_tasks.append(asyncio.create_task(self._read_stream(stderr, "stderr")))

    async def close(self) -> None:
        tasks = list(self._reader_tasks)
        self._reader_tasks = []
        for task in tasks:
            if task and not task.done():
                task.cancel()
        for task in tasks:
            if task is None:
                continue
            try:
                await task
            except asyncio.CancelledError:
                pass
            except Exception:
                logger.debug("hidden PTY reader shutdown failed", exc_info=True)
        proc = self.proc
        self.proc = None
        self.output = ""
        self.cwd = ""
        self._exit_futures.clear()
        if proc is not None:
            await close_ssh_handle(proc)

    async def run_command(self, command: str, *, timeout: float = DEFAULT_TIMEOUT_SEC) -> tuple[int, str]:
        """Type one command into the hidden PTY and wait for the exit marker."""

        text = str(command or "").strip()
        if not text:
            return -1, ""
        if self.proc is None:
            return -1, "hidden PTY is not attached"

        # Hold the lock for the full command lifecycle so a timed-out
        # foreground process cannot leave later stdin writes queued behind it.
        async with self._lock:
            cmd_id = int(self.next_id)
            self.next_id += 1
            loop = asyncio.get_running_loop()
            future: asyncio.Future[int] = loop.create_future()
            self._exit_futures[cmd_id] = future
            output_at = len(self.output)
            stdin = getattr(self.proc, "stdin", None)
            if stdin is None:
                self._exit_futures.pop(cmd_id, None)
                return -1, "hidden PTY stdin unavailable"
            stdin.write(text + "\n")
            var = f"{NOVA_PTY_MARKER_PREFIX}{cmd_id}"
            marker_cmd = f'{var}=$?; echo "{NOVA_PTY_MARKER_PREFIX}{cmd_id}:${{{var}}}__"'
            stdin.write(marker_cmd + "\n")

            try:
                exit_code = int(await asyncio.wait_for(future, timeout=max(1.0, float(timeout))))
            except TimeoutError:
                self._exit_futures.pop(cmd_id, None)
                snippet = self.output[output_at:][-OUTPUT_LIMIT:]
                interrupted = await self._interrupt_and_resync()
                # #region agent log
                try:
                    import json as _json
                    import time as _time
                    from pathlib import Path as _Path

                    _log = {
                        "sessionId": "a0b238",
                        "runId": "post-fix",
                        "hypothesisId": "F",
                        "location": "hidden_pty.py:timeout_124",
                        "message": "hidden PTY command timeout -> exit 124",
                        "data": {
                            "timeout_sec": float(timeout),
                            "cmd_preview": text[:200],
                            "snippet_chars": len(snippet or ""),
                            "interrupted": bool(interrupted),
                        },
                        "timestamp": int(_time.time() * 1000),
                    }
                    for _p in (_Path("/workspace/debug-a0b238.log"), _Path(__file__).resolve().parents[3] / "debug-a0b238.log"):
                        try:
                            with _p.open("a", encoding="utf-8") as _f:
                                _f.write(_json.dumps(_log, ensure_ascii=False) + "\n")
                            break
                        except Exception:
                            continue
                except Exception:
                    pass
                # #endregion
                return 124, snippet or f"TIMEOUT after {timeout:.0f}s"
            except asyncio.CancelledError:
                self._exit_futures.pop(cmd_id, None)
                raise
            finally:
                self._exit_futures.pop(cmd_id, None)

            snippet = self.output[output_at:][-OUTPUT_LIMIT:]
            self.apply_cwd_from_command(text, exit_code)
            return exit_code, snippet

    async def _interrupt_and_resync(self) -> bool:
        """Best-effort: interrupt a hung foreground command and re-sync the shell.

        Without this, a stuck ``docker``/sudo call leaves the hidden PTY wedged
        and every subsequent ``run_command`` times out with empty output.
        """
        stdin = getattr(self.proc, "stdin", None) if self.proc is not None else None
        if stdin is None:
            return False
        try:
            # SIGINT twice, then SIGQUIT — mirrors interactive terminal recovery.
            stdin.write("\x03")
            await asyncio.sleep(0.15)
            stdin.write("\x03")
            await asyncio.sleep(0.15)
            stdin.write("\x1c")
            await asyncio.sleep(0.1)

            sync_id = int(self.next_id)
            self.next_id += 1
            loop = asyncio.get_running_loop()
            future: asyncio.Future[int] = loop.create_future()
            self._exit_futures[sync_id] = future
            stdin.write(f'echo "{NOVA_PTY_MARKER_PREFIX}{sync_id}:0__"\n')
            try:
                await asyncio.wait_for(future, timeout=3.0)
                return True
            except TimeoutError:
                logger.warning("hidden PTY resync after timeout failed (cmd still wedged?)")
                return False
            finally:
                self._exit_futures.pop(sync_id, None)
        except Exception:
            logger.debug("hidden PTY interrupt/resync failed", exc_info=True)
            return False

    def apply_cwd_from_command(self, command: str, exit_code: int | None) -> None:
        from servers.services.terminal_ai.session_context import apply_successful_command_context

        updated = apply_successful_command_context(
            {"cwd": self.cwd},
            command=command,
            exit_code=exit_code,
        )
        self.cwd = str(updated.get("cwd") or self.cwd or "")

    async def bootstrap_cwd(self) -> None:
        from servers.services.terminal_ai.session_context import (
            build_initial_session_context,
            build_session_probe_command,
        )

        try:
            _code, output = await self.run_command(build_session_probe_command(), timeout=8.0)
        except Exception:
            logger.debug("hidden PTY cwd probe failed", exc_info=True)
            return
        parsed = build_initial_session_context(output)
        cwd = str(parsed.get("cwd") or "").strip()
        if cwd:
            self.cwd = cwd

    async def _read_stream(self, reader: Any, stream: str) -> None:
        try:
            while True:
                chunk = await reader.read(4096)
                if not chunk:
                    break
                filtered, markers = filter_internal_markers(
                    stream=stream,
                    data=chunk,
                    marker_prefix=NOVA_PTY_MARKER_PREFIX,
                    marker_suppress=self._marker_suppress,
                    marker_line_buf=self._marker_line_buf,
                )
                if filtered:
                    self.output = append_clean_output(self.output, filtered, limit=OUTPUT_LIMIT)
                for cmd_id, exit_code in markers:
                    future = self._exit_futures.get(int(cmd_id))
                    if future is not None and not future.done():
                        future.set_result(int(exit_code))
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.debug("hidden PTY stream %s failed", stream, exc_info=True)


async def ensure_hidden_pty(session: HiddenPtySession | None, conn: Any) -> HiddenPtySession:
    """Attach a hidden PTY if needed and return the live session."""

    current = session if session is not None else HiddenPtySession()
    if not current.attached:
        await current.attach(conn)
        await current.bootstrap_cwd()
    return current
