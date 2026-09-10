from __future__ import annotations

import stat
from types import SimpleNamespace

import asyncssh
import pytest

from servers.services.terminal_snapshotting import capture_pre_execution_snapshot


class FakeSFTP:
    def __init__(self, content=b"", *, error=None, mode=stat.S_IFREG, size=None):
        self.content = content
        self.error = error
        self.mode = mode
        self.size = len(content) if size is None else size
        self.paths = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    async def lstat(self, path):
        self.paths.append(path)
        if self.error:
            raise self.error
        return SimpleNamespace(permissions=self.mode, size=self.size)

    def open(self, path, mode):
        assert mode == "rb"
        assert path == self.paths[-1]
        return self

    async def read(self, limit):
        return self.content[:limit]


class FakeConn:
    def __init__(self, sftp):
        self.sftp = sftp

    def start_sftp_client(self):
        return self.sftp


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "sftp,expected",
    [
        (FakeSFTP(b"no final newline"), ("no final newline", True)),
        (FakeSFTP(b""), ("", True)),
        (FakeSFTP(error=asyncssh.SFTPNoSuchFile("missing")), ("", False)),
        (FakeSFTP(error=asyncssh.SFTPPermissionDenied("denied")), None),
        (FakeSFTP(mode=stat.S_IFDIR), None),
        (FakeSFTP(mode=stat.S_IFLNK), None),
        (FakeSFTP(b"binary\xff"), None),
        (FakeSFTP(b"x" * 1001), None),
        (FakeSFTP(b"x" * 1001, size=1), None),
    ],
)
async def test_capture_distinguishes_empty_missing_and_unreadable(monkeypatch, sftp, expected):
    saved = []
    path = "/tmp/$(touch_injection)"
    monkeypatch.setattr("servers.services.snapshot_service.detect_target_file", lambda _: path)
    monkeypatch.setattr("servers.services.snapshot_service.MAX_SNAPSHOT_BYTES", 1000)
    monkeypatch.setattr("servers.services.snapshot_service.save_snapshot", lambda **kw: saved.append(kw))
    result = await capture_pre_execution_snapshot(
        command="tee /tmp/file", cmd_id=9, ssh_conn=FakeConn(sftp), server_id=1, user_id=2,
    )
    assert result is (expected is not None)
    assert sftp.paths == [path]  # Literal SFTP path, never interpolated in a shell.
    if expected is None:
        assert saved == []
    else:
        assert saved == [{
            "server_id": 1, "user_id": 2, "command": "tee /tmp/file",
            "file_path": path, "content": expected[0], "file_existed": expected[1],
        }]


@pytest.mark.asyncio
async def test_capture_skips_when_no_target():
    assert not await capture_pre_execution_snapshot(
        command="ls", cmd_id=1, ssh_conn=FakeConn(FakeSFTP()), server_id=1, user_id=2,
    )
