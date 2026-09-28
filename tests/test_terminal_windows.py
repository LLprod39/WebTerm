from __future__ import annotations

from types import SimpleNamespace

import pytest

from servers.os_detect import windows_caption_from_probe
from servers.services.terminal_windows import (
    build_session_prelude,
    normalize_windows_pty_input,
)


def test_windows_prelude_sets_utf8_and_skips_bash_export():
    server = SimpleNamespace(os_type="windows")
    prelude = build_session_prelude(server, {"LANG": "ru", "BAD-NAME": "x", "NOTE": "a'b"})

    assert prelude.endswith("\r")
    assert "export " not in prelude
    assert "chcp 65001" in prelude
    assert "[Console]::OutputEncoding" in prelude
    assert "$env:LANG = 'ru'" in prelude
    assert "$env:NOTE = 'a''b'" in prelude
    assert "BAD-NAME" not in prelude


def test_linux_prelude_keeps_bash_exports():
    server = SimpleNamespace(os_type="linux")
    prelude = build_session_prelude(server, {"LANG": "C"})
    assert prelude == "export LANG=C\n"


def test_linux_prelude_is_empty_without_env():
    assert build_session_prelude(SimpleNamespace(os_type="linux"), {}) == ""


def test_normalize_windows_pty_input_rewrites_lone_lf():
    assert normalize_windows_pty_input("dir\n") == "dir\r"
    assert normalize_windows_pty_input("dir\r") == "dir\r"
    assert normalize_windows_pty_input("dir\r\n") == "dir\r\n"
    assert normalize_windows_pty_input("a\nb\r\nc") == "a\rb\r\nc"


def test_windows_caption_from_probe_prefers_os_line():
    raw = "\nMicrosoft Windows Server 2022 Datacenter\n"
    assert windows_caption_from_probe(raw) == "Microsoft Windows Server 2022 Datacenter"
    assert windows_caption_from_probe("Managed secret cannot be decrypted") == ""


@pytest.mark.django_db
def test_windows_os_detect_keeps_windows_when_caption_probe_fails(django_user_model, monkeypatch):
    from asgiref.sync import async_to_sync

    from servers.models import Server
    from servers.os_detect import detect_server_os

    user = django_user_model.objects.create_user(username="win-os", password="x")
    server = Server.objects.create(
        user=user,
        name="win-01",
        host="10.1.0.8",
        port=22,
        username="Administrator",
        server_type="ssh",
        os_type="windows",
        detected_os="windows",
    )

    async def fail_probe(*_args, **_kwargs):
        raise RuntimeError("ssh down")

    monkeypatch.setattr("servers.os_detect.get_server_auth_secret", lambda _server: "")
    monkeypatch.setattr("servers.os_detect._run_detect_command", fail_probe)

    result = async_to_sync(detect_server_os)(server)
    server.refresh_from_db()

    assert result["detected_os"] == "windows"
    assert result["success"] is True
    assert server.detected_os == "windows"
    assert server.detected_os_meta["source"] == "os_type"
    assert "ssh down" in server.detected_os_meta["probe_error"]
