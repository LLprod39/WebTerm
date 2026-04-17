"""Tests for the exec_direct (non-PTY) execution path (F2-8 v2).

We exercise :meth:`SSHTerminalConsumer._ai_execute_command_direct` with a
mocked ``asyncssh.SSHClientConnection`` so the tests run without any real
SSH. The consumer's ``_send_ai_event`` is captured into a list for
assertions.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from servers.consumers.ssh_terminal import SSHTerminalConsumer


class _FakeConn:
    """Minimal asyncssh.SSHClientConnection-like stub for direct exec.

    Captures the last ``run`` invocation so tests can inspect what was sent.
    """

    def __init__(self, *, stdout: str = "", stderr: str = "", exit_status: int | None = 0, raise_exc: Exception | None = None):
        self._stdout = stdout
        self._stderr = stderr
        self._exit_status = exit_status
        self._raise_exc = raise_exc
        self.last_cmd: str | None = None
        self.last_check: bool | None = None

    async def run(self, cmd, *, check=False):  # noqa: ANN001, ANN002
        self.last_cmd = cmd
        self.last_check = check
        if self._raise_exc is not None:
            raise self._raise_exc
        return SimpleNamespace(stdout=self._stdout, stderr=self._stderr, exit_status=self._exit_status)


def _make_consumer(conn: _FakeConn | None) -> tuple[SSHTerminalConsumer, list[dict]]:
    """Build a bare consumer with enough state for direct-exec tests."""
    cons = SSHTerminalConsumer.__new__(SSHTerminalConsumer)
    cons._ssh_conn = conn  # type: ignore[attr-defined]
    cons._ssh_proc = None  # PTY not used in direct path  # type: ignore[attr-defined]
    sent: list[dict] = []

    async def _capture(event):
        sent.append(event)

    cons._send_ai_event = _capture  # type: ignore[assignment]
    return cons, sent


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


class TestExecDirectHappyPath:
    def test_returns_stdout_and_zero_exit_code(self):
        conn = _FakeConn(stdout="Filesystem  Size\n/dev/sda1  50G\n", exit_status=0)
        cons, sent = _make_consumer(conn)

        exit_code, output = _run(cons._ai_execute_command_direct("df -h", 42))

        assert exit_code == 0
        assert "Filesystem" in output
        assert conn.last_cmd == "df -h"
        assert conn.last_check is False  # we never raise on non-zero
        # Exactly one UI event carrying the captured output + metadata.
        assert len(sent) == 1
        evt = sent[0]
        assert evt["type"] == "ai_direct_output"
        assert evt["id"] == 42
        assert evt["cmd"] == "df -h"
        assert evt["exit_code"] == 0

    def test_combines_stderr_with_stdout(self):
        conn = _FakeConn(stdout="data\n", stderr="warn\n", exit_status=0)
        cons, _ = _make_consumer(conn)

        _exit, output = _run(cons._ai_execute_command_direct("echo data", 1))

        assert "data" in output
        assert "warn" in output


class TestExecDirectEdgeCases:
    def test_non_zero_exit_preserved(self):
        conn = _FakeConn(stdout="", stderr="not found\n", exit_status=127)
        cons, sent = _make_consumer(conn)

        exit_code, output = _run(cons._ai_execute_command_direct("nosuch", 7))

        assert exit_code == 127
        assert "not found" in output
        assert sent[0]["exit_code"] == 127

    def test_timeout_maps_to_124(self):
        # Sleep longer than DIRECT_EXEC_TIMEOUT_SEC — we patch the constant
        # to keep the test fast.
        class _SlowConn(_FakeConn):
            async def run(self, cmd, *, check=False):  # noqa: ANN001, ANN002
                await asyncio.sleep(5)
                return SimpleNamespace(stdout="", stderr="", exit_status=0)

        cons, _ = _make_consumer(_SlowConn())
        cons.DIRECT_EXEC_TIMEOUT_SEC = 0.05  # force timeout

        exit_code, output = _run(cons._ai_execute_command_direct("sleep 5", 99))

        assert exit_code == 124
        assert "timed out" in output

    def test_no_connection_raises(self):
        cons, _ = _make_consumer(None)
        with pytest.raises(RuntimeError, match="SSH connection"):
            _run(cons._ai_execute_command_direct("ls", 1))

    def test_empty_command_returns_minus_one(self):
        cons, sent = _make_consumer(_FakeConn())
        exit_code, output = _run(cons._ai_execute_command_direct("   ", 1))
        # We short-circuit before issuing a run and before emitting an event.
        assert (exit_code, output) == (-1, "")
        assert sent == []

    def test_output_truncated_to_cap(self):
        big = "x" * 20000
        conn = _FakeConn(stdout=big, exit_status=0)
        cons, _ = _make_consumer(conn)

        _exit, output = _run(cons._ai_execute_command_direct("cat big", 1))

        # DIRECT_EXEC_MAX_OUTPUT defaults to 6000.
        assert len(output) == cons.DIRECT_EXEC_MAX_OUTPUT

    def test_null_exit_status_maps_to_one(self):
        conn = _FakeConn(stdout="ok", exit_status=None)
        cons, _ = _make_consumer(conn)

        exit_code, _output = _run(cons._ai_execute_command_direct("weird", 1))

        assert exit_code == 1


class TestExecDirectDoesNotTouchPTY:
    def test_pty_stdin_never_written(self):
        pty_writes: list[str] = []

        class _FakeStdin:
            def write(self, data):  # noqa: ANN001
                pty_writes.append(str(data))

        class _FakeProc:
            stdin = _FakeStdin()

        conn = _FakeConn(stdout="ok", exit_status=0)
        cons, _ = _make_consumer(conn)
        cons._ssh_proc = _FakeProc()  # type: ignore[assignment]

        _run(cons._ai_execute_command_direct("ls", 1))

        assert pty_writes == [], "direct exec must NOT touch the interactive PTY stdin"
