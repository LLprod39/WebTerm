from __future__ import annotations

from types import SimpleNamespace

import pytest

import servers.services.terminal_ssh_lifecycle as mod
from servers.services.terminal_input import TerminalSize
from servers.services.terminal_ssh_lifecycle import (
    close_terminal_ssh_session,
    open_terminal_ssh_session,
    resize_terminal_ssh_session,
)


class FakeProc:
    def __init__(self):
        self.closed = False
        self.waited = False
        self.resize_calls: list[tuple[int, int]] = []

    def change_terminal_size(self, cols: int, rows: int):
        self.resize_calls.append((cols, rows))

    def close(self):
        self.closed = True

    async def wait_closed(self):
        self.waited = True


class FakeConn:
    def __init__(self, proc: FakeProc):
        self.proc = proc
        self.closed = False
        self.waited = False
        self.create_kwargs: dict | None = None

    async def create_process(self, **kwargs):
        self.create_kwargs = kwargs
        return self.proc

    def close(self):
        self.closed = True

    async def wait_closed(self):
        self.waited = True


@pytest.mark.asyncio
async def test_open_terminal_ssh_session_builds_pty_process(monkeypatch):
    proc = FakeProc()
    conn = FakeConn(proc)
    calls: dict[str, object] = {}

    async def fake_build_kwargs(server, *, secret):  # noqa: ANN001
        calls["server"] = server
        calls["secret"] = secret
        return {"host": server.host}

    async def fake_connect(**kwargs):
        calls["connect_kwargs"] = kwargs
        return conn

    monkeypatch.setattr(mod, "build_terminal_connect_kwargs", fake_build_kwargs)
    server = SimpleNamespace(host="10.0.0.80", port=22)

    opened = await open_terminal_ssh_session(
        server=server,
        secret="secret",
        term_type="xterm-256color",
        term_size=TerminalSize(cols=120, rows=40),
        connect_factory=fake_connect,
    )

    assert opened.conn is conn
    assert opened.proc is proc
    assert calls["server"] is server
    assert calls["secret"] == "secret"
    assert calls["connect_kwargs"] == {"host": "10.0.0.80"}
    assert conn.create_kwargs == {
        "term_type": "xterm-256color",
        "term_size": (120, 40, 0, 0),
        "encoding": "utf-8",
        "errors": "replace",
    }


def test_resize_terminal_ssh_session_ignores_invalid_size():
    proc = FakeProc()

    resize_terminal_ssh_session(proc, TerminalSize(cols=0, rows=24))
    resize_terminal_ssh_session(proc, TerminalSize(cols=100, rows=30))

    assert proc.resize_calls == [(100, 30)]


@pytest.mark.asyncio
async def test_close_terminal_ssh_session_closes_proc_then_conn():
    proc = FakeProc()
    conn = FakeConn(proc)

    await close_terminal_ssh_session(conn, proc)

    assert proc.closed is True
    assert proc.waited is True
    assert conn.closed is True
    assert conn.waited is True
