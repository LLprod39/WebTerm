"""Unit tests for the MCP Runner session manager.

These spawn the bundled stdio demo MCP server so they exercise real subprocess
framing, session reuse, idle reaping and LRU eviction without needing FastAPI.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from mcp_runner.config import RunnerConfig
from mcp_runner.sessions import SessionManager, spec_fingerprint

REPO_ROOT = Path(__file__).resolve().parents[1]
DEMO_SERVER = str(REPO_ROOT / "studio" / "demo_mcp_server.py")


def _demo_spec(marker: str = "") -> dict:
    return {"command": sys.executable, "args": [DEMO_SERVER], "env": ({"DEMO_MARKER": marker} if marker else {})}


def _config(**overrides) -> RunnerConfig:
    config = RunnerConfig()
    config.session_ttl_seconds = overrides.get("session_ttl_seconds", 300)
    config.max_sessions = overrides.get("max_sessions", 50)
    config.reap_interval_seconds = 5
    config.initialize_timeout_seconds = 20
    config.request_timeout_seconds = 30
    config.terminate_timeout_seconds = 3
    return config


@pytest.mark.asyncio
async def test_session_initializes_and_reuses_process():
    manager = SessionManager(_config())
    spec = _demo_spec()
    try:
        info = await manager.rpc("srv-1", spec, "initialize")
        assert info["serverInfo"]["name"] == "studio-local-demo"

        first_pid = manager._sessions["srv-1"].proc.pid

        listed = await manager.rpc("srv-1", spec, "tools/list")
        assert isinstance(listed.get("tools"), list) and listed["tools"]

        # Second call must reuse the same live process (no cold start).
        listed_again = await manager.rpc("srv-1", spec, "tools/list")
        assert isinstance(listed_again.get("tools"), list)
        assert manager._sessions["srv-1"].proc.pid == first_pid
    finally:
        await manager.shutdown()
    assert manager._sessions == {}


@pytest.mark.asyncio
async def test_changed_spec_respawns_process():
    manager = SessionManager(_config())
    try:
        await manager.rpc("srv-1", _demo_spec("a"), "initialize")
        old_pid = manager._sessions["srv-1"].proc.pid
        await manager.rpc("srv-1", _demo_spec("b"), "initialize")
        new_pid = manager._sessions["srv-1"].proc.pid
        assert new_pid != old_pid
        assert spec_fingerprint(_demo_spec("a")) != spec_fingerprint(_demo_spec("b"))
    finally:
        await manager.shutdown()


@pytest.mark.asyncio
async def test_idle_sessions_are_reaped():
    manager = SessionManager(_config(session_ttl_seconds=0))
    try:
        await manager.rpc("srv-1", _demo_spec(), "initialize")
        assert "srv-1" in manager._sessions
        reaped = await manager.reap_idle()
        assert reaped == 1
        assert manager._sessions == {}
    finally:
        await manager.shutdown()


@pytest.mark.asyncio
async def test_lru_eviction_when_pool_is_full():
    manager = SessionManager(_config(max_sessions=1))
    try:
        await manager.rpc("srv-1", _demo_spec("1"), "initialize")
        await manager.rpc("srv-2", _demo_spec("2"), "initialize")
        assert list(manager._sessions) == ["srv-2"]
    finally:
        await manager.shutdown()
