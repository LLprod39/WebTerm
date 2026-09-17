from __future__ import annotations

import asyncio
import re

import pytest

from servers.services.terminal_ai.hidden_pty import (
    NOVA_PTY_MARKER_PREFIX,
    HiddenPtySession,
    ensure_hidden_pty,
)


class FakeStdin:
    def __init__(self, proc: FakeProc) -> None:
        self.proc = proc
        self.writes: list[str] = []

    def write(self, data: str) -> None:
        self.writes.append(str(data))
        self.proc.on_stdin(str(data))


class FakeReader:
    def __init__(self) -> None:
        self._queue: asyncio.Queue[str] = asyncio.Queue()

    async def read(self, _n: int) -> str:
        return await self._queue.get()

    def push(self, data: str) -> None:
        self._queue.put_nowait(data)


class FakeProc:
    def __init__(self) -> None:
        self.stdout = FakeReader()
        self.stderr = FakeReader()
        self.stdin = FakeStdin(self)
        self.closed = False
        self.last_command = ""

    def on_stdin(self, data: str) -> None:
        if NOVA_PTY_MARKER_PREFIX in data and "echo" in data:
            match = re.search(rf"{re.escape(NOVA_PTY_MARKER_PREFIX)}(\d+):", data)
            if not match:
                return
            cmd_id = match.group(1)
            output = ""
            if "printf '__NOVA_CTX__" in self.last_command or "__NOVA_CTX__" in self.last_command:
                output = "__NOVA_CTX__cwd=/srv/app\n"
            elif self.last_command.strip() == "pwd":
                output = f"{self.cwd_value()}\n"
            self.stdout.push(f"{output}{NOVA_PTY_MARKER_PREFIX}{cmd_id}:0__\n")
            return
        text = data.strip()
        if text:
            self.last_command = text

    def cwd_value(self) -> str:
        if self.last_command.startswith("cd "):
            return self.last_command.split(None, 1)[1]
        return "/srv/app"

    def close(self) -> None:
        self.closed = True
        self.stdout.push("")
        self.stderr.push("")

    async def wait_closed(self) -> None:
        return None


class FakeConn:
    def __init__(self) -> None:
        self.processes: list[FakeProc] = []

    async def create_process(self, **_kwargs):
        proc = FakeProc()
        self.processes.append(proc)
        return proc


@pytest.mark.asyncio
async def test_two_create_process_calls_on_one_conn():
    conn = FakeConn()
    human = await conn.create_process(term_type="xterm")
    nova = await ensure_hidden_pty(None, conn)
    try:
        assert len(conn.processes) == 2
        assert nova.proc is conn.processes[1]
        assert nova.proc is not human
    finally:
        await nova.close()


@pytest.mark.asyncio
async def test_cd_persists_for_next_shell_call():
    conn = FakeConn()
    session = await ensure_hidden_pty(None, conn)
    try:
        code, _output = await session.run_command("cd /tmp")
        assert code == 0
        assert session.cwd == "/tmp"
        code, _output = await session.run_command("pwd")
        assert code == 0
        assert session.cwd == "/tmp"
    finally:
        await session.close()


@pytest.mark.asyncio
async def test_human_proc_does_not_see_nova_stdin():
    conn = FakeConn()
    human = await conn.create_process()
    session = await ensure_hidden_pty(None, conn)
    try:
        await session.run_command("echo nova-only")
        assert "echo nova-only" not in "".join(human.stdin.writes)
        assert any("echo nova-only" in chunk for chunk in session.proc.stdin.writes)
    finally:
        await session.close()
