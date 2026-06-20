from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from servers.services.terminal_direct_execution import execute_direct_terminal_command


class FakeConn:
    def __init__(self, *, stdout: str = "", stderr: str = "", exit_status: int | None = 0) -> None:
        self.stdout = stdout
        self.stderr = stderr
        self.exit_status = exit_status
        self.last_cmd: str | None = None
        self.last_check: bool | None = None

    async def run(self, cmd: str, *, check: bool = False):
        self.last_cmd = cmd
        self.last_check = check
        return SimpleNamespace(stdout=self.stdout, stderr=self.stderr, exit_status=self.exit_status)


async def _send(events: list[dict], event: dict) -> None:
    events.append(event)


@pytest.mark.asyncio
async def test_execute_direct_terminal_command_emits_output_event():
    events: list[dict] = []
    conn = FakeConn(stdout="ok\n", stderr="warn\n", exit_status=7)

    exit_code, output = await execute_direct_terminal_command(
        ssh_conn=conn,
        command=" df -h ",
        item_id=42,
        send_event=lambda event: _send(events, event),
        normalize_command=lambda value: value.strip(),
    )

    assert exit_code == 7
    assert output == "ok\n\nwarn\n"
    assert conn.last_cmd == "df -h"
    assert conn.last_check is False
    assert events == [
        {
            "type": "ai_direct_output",
            "id": 42,
            "cmd": "df -h",
            "output": "ok\n\nwarn\n",
            "exit_code": 7,
            "dry_run": False,
        }
    ]


@pytest.mark.asyncio
async def test_execute_direct_terminal_command_handles_timeout_without_event_loss():
    events: list[dict] = []

    class SlowConn(FakeConn):
        async def run(self, cmd: str, *, check: bool = False):  # noqa: ARG002
            await asyncio.sleep(5)
            return SimpleNamespace(stdout="", stderr="", exit_status=0)

    exit_code, output = await execute_direct_terminal_command(
        ssh_conn=SlowConn(),
        command="sleep 5",
        item_id=99,
        send_event=lambda event: _send(events, event),
        normalize_command=lambda value: value.strip(),
        timeout_seconds=0.01,
    )

    assert exit_code == 124
    assert "timed out" in output
    assert events[0]["exit_code"] == 124


@pytest.mark.asyncio
async def test_execute_direct_terminal_command_short_circuits_empty_command():
    events: list[dict] = []

    result = await execute_direct_terminal_command(
        ssh_conn=FakeConn(),
        command=" ",
        item_id=1,
        send_event=lambda event: _send(events, event),
        normalize_command=lambda _value: "",
    )

    assert result == (-1, "")
    assert events == []
