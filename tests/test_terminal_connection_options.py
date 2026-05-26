from __future__ import annotations

from types import SimpleNamespace

import pytest

import servers.services.terminal_connection_options as mod
from servers.services.terminal_connection_options import build_terminal_connect_kwargs


@pytest.mark.asyncio
async def test_build_terminal_connect_kwargs_resolves_known_hosts_and_settings(monkeypatch, settings):
    server = SimpleNamespace(id=123, host="10.0.0.70")
    calls: dict[str, object] = {}

    async def fake_known_hosts(target):
        calls["known_hosts_target"] = target
        return "/tmp/known_hosts"

    def fake_build_kwargs(target, **kwargs):
        calls["build_target"] = target
        calls["kwargs"] = kwargs
        return {"host": target.host, **kwargs}

    monkeypatch.setattr(mod, "ensure_server_known_hosts", fake_known_hosts)
    monkeypatch.setattr(mod, "build_server_connect_kwargs", fake_build_kwargs)
    settings.SSH_CONNECT_TIMEOUT_SECONDS = 0
    settings.SSH_LOGIN_TIMEOUT_SECONDS = 30
    settings.SSH_KEEPALIVE_INTERVAL_SECONDS = 0
    settings.SSH_KEEPALIVE_COUNT_MAX = 4

    result = await build_terminal_connect_kwargs(server, secret="secret")

    assert calls["known_hosts_target"] is server
    assert calls["build_target"] is server
    assert result["host"] == "10.0.0.70"
    assert result["secret"] == "secret"
    assert result["known_hosts"] == "/tmp/known_hosts"
    assert result["connect_timeout"] == 10
    assert result["login_timeout"] == 30
    assert result["keepalive_interval"] == 20
    assert result["keepalive_count_max"] == 4


@pytest.mark.asyncio
async def test_build_terminal_connect_kwargs_normalizes_empty_secret(monkeypatch):
    server = SimpleNamespace(id=123, host="10.0.0.70")

    async def fake_known_hosts(_target):
        return None

    def fake_build_kwargs(_target, **kwargs):
        return kwargs

    monkeypatch.setattr(mod, "ensure_server_known_hosts", fake_known_hosts)
    monkeypatch.setattr(mod, "build_server_connect_kwargs", fake_build_kwargs)

    result = await build_terminal_connect_kwargs(server, secret="")

    assert result["secret"] == ""
