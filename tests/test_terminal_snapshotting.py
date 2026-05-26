from __future__ import annotations

from types import SimpleNamespace

import pytest

from servers.services.terminal_snapshotting import capture_pre_execution_snapshot


class FakeConn:
    def __init__(self, stdout: str):
        self.stdout = stdout
        self.commands: list[tuple[str, bool]] = []

    async def run(self, command: str, *, check: bool):
        self.commands.append((command, check))
        return SimpleNamespace(stdout=self.stdout)


@pytest.mark.asyncio
async def test_capture_pre_execution_snapshot_saves_detected_file(monkeypatch):
    saved: list[dict] = []

    monkeypatch.setattr(
        "servers.services.snapshot_service.detect_target_file",
        lambda _command: "/etc/nginx/nginx.conf",
    )
    monkeypatch.setattr("servers.services.snapshot_service.MAX_SNAPSHOT_BYTES", 1000)
    monkeypatch.setattr(
        "servers.services.snapshot_service.save_snapshot",
        lambda **kwargs: saved.append(kwargs),
    )
    conn = FakeConn("worker_processes auto;")

    result = await capture_pre_execution_snapshot(
        command="sudo tee /etc/nginx/nginx.conf",
        cmd_id=9,
        ssh_conn=conn,
        server_id=1,
        user_id=2,
    )

    assert result is True
    assert conn.commands == [("cat /etc/nginx/nginx.conf 2>/dev/null", False)]
    assert saved == [
        {
            "server_id": 1,
            "user_id": 2,
            "command": "sudo tee /etc/nginx/nginx.conf",
            "file_path": "/etc/nginx/nginx.conf",
            "content": "worker_processes auto;",
        }
    ]


@pytest.mark.asyncio
async def test_capture_pre_execution_snapshot_skips_when_no_target(monkeypatch):
    monkeypatch.setattr("servers.services.snapshot_service.detect_target_file", lambda _command: "")

    result = await capture_pre_execution_snapshot(
        command="ls",
        cmd_id=1,
        ssh_conn=FakeConn(""),
        server_id=1,
        user_id=2,
    )

    assert result is False


@pytest.mark.asyncio
async def test_capture_pre_execution_snapshot_skips_large_content(monkeypatch):
    saved: list[dict] = []
    monkeypatch.setattr(
        "servers.services.snapshot_service.detect_target_file",
        lambda _command: "/tmp/large",
    )
    monkeypatch.setattr("servers.services.snapshot_service.MAX_SNAPSHOT_BYTES", 3)
    monkeypatch.setattr(
        "servers.services.snapshot_service.save_snapshot",
        lambda **kwargs: saved.append(kwargs),
    )

    result = await capture_pre_execution_snapshot(
        command="tee /tmp/large",
        cmd_id=1,
        ssh_conn=FakeConn("abcd"),
        server_id=1,
        user_id=2,
    )

    assert result is False
    assert saved == []
