"""Unit tests for elevated file path validation and error classification."""

from __future__ import annotations

import asyncio
import shlex
from types import SimpleNamespace

import pytest

from servers import elevated_files
from servers.elevated_files import ElevatedFileError, _classify_sudo_failure, _validate_remote_path


def test_validate_remote_path_accepts_absolute():
    assert _validate_remote_path("/etc/nginx/nginx.conf") == "/etc/nginx/nginx.conf"


def test_validate_remote_path_rejects_empty():
    with pytest.raises(ValueError):
        _validate_remote_path("  ")


def test_validate_remote_path_rejects_null_byte():
    with pytest.raises(ValueError):
        _validate_remote_path("/etc/pass\x00wd")


def test_validate_remote_path_rejects_directory_trailing_slash():
    with pytest.raises(ValueError):
        _validate_remote_path("/etc/nginx/")


def test_classify_sudo_required():
    err = _classify_sudo_failure("sudo: a password is required", 1, had_password=False)
    assert isinstance(err, ElevatedFileError)
    assert err.code == "sudo_required"


def test_classify_permission_denied():
    err = _classify_sudo_failure("Permission denied", 1, had_password=True)
    assert err.code == "permission_denied"


@pytest.mark.parametrize(
    "path",
    [
        "/etc/webterm config/app.conf",
        "/tmp/quoted'file.conf",
        "/tmp/config; printf injected",
        "/tmp/config$(printf injected)",
        "/tmp/config`printf injected`",
        "/tmp/config\nnext-line",
    ],
)
def test_elevated_write_quotes_the_path_inside_the_remote_shell(monkeypatch, path):
    captured = {}

    async def capture_command(server, **kwargs):
        captured.update(kwargs)
        return {"success": True, "stdout": "", "stderr": "", "exit_code": 0}

    monkeypatch.setattr(elevated_files, "_run_elevated", capture_command)
    result = asyncio.run(elevated_files.write_text_file_elevated(SimpleNamespace(), path=path, content="saved text"))
    # Parse the two shell layers without executing any process or remote command.
    outer = shlex.split(captured["command"])
    assert outer[:2] == ["sh", "-c"]
    assert len(outer) == 3
    assert outer[2] == f"base64 -d > {shlex.quote(path)}"
    assert shlex.split(outer[2]) == ["base64", "-d", ">", path]
    assert result["path"] == path
    assert captured["input_text"] == "c2F2ZWQgdGV4dA==\n"
