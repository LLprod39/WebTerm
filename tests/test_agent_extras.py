"""Integration tests for the agent's multi-target context:

- ``ensure_connection`` opens a lazy SSH connection via ``open_target``.
- ``shell`` tool routes to the correct target once connected.
- Unknown target names surface as tool errors without crashing.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from servers.services.terminal_ai.agent.tools import (
    ServerTarget,
    ShellArgs,
    ShellTool,
    ToolContext,
)


@dataclass
class FakeRunResult:
    stdout: str = ""
    stderr: str = ""
    exit_status: int | None = 0


class FakeConn:
    def __init__(self, label: str, default: FakeRunResult | None = None):
        self.label = label
        self.default = default or FakeRunResult(stdout=f"hi-from-{label}")
        self.calls: list[str] = []
        self.closed = False

    async def run(self, cmd: str, **_: Any) -> FakeRunResult:
        self.calls.append(cmd)
        return self.default

    def close(self) -> None:
        self.closed = True


class TestLazyExtrasConnect:
    @pytest.mark.asyncio
    async def test_open_target_called_on_first_use(self):
        primary_conn = FakeConn("primary")
        primary = ServerTarget(
            name="primary",
            server_id=1,
            ssh_conn=primary_conn,
            is_primary=True,
        )
        # Extra has no ssh_conn yet — should be opened lazily.
        extra = ServerTarget(
            name="worker-1",
            server_id=2,
            ssh_conn=None,
            is_primary=False,
        )
        opened: list[str] = []
        extra_conn = FakeConn("worker-1")

        async def open_target(name: str) -> Any | None:
            opened.append(name)
            if name == "worker-1":
                return extra_conn
            return None

        ctx = ToolContext(
            primary=primary,
            extras={"worker-1": extra},
            open_target=open_target,
        )

        result = await ShellTool().run(
            ShellArgs(cmd="hostname", target="worker-1"), ctx
        )
        assert result.ok is True
        assert "hi-from-worker-1" in result.output
        assert opened == ["worker-1"]  # open_target invoked exactly once
        assert extra.ssh_conn is extra_conn  # cached back onto target

    @pytest.mark.asyncio
    async def test_second_use_reuses_cached_connection(self):
        primary = ServerTarget(
            name="primary",
            server_id=1,
            ssh_conn=FakeConn("primary"),
            is_primary=True,
        )
        extra_conn = FakeConn("worker-1")
        extra = ServerTarget(
            name="worker-1", server_id=2, ssh_conn=None, is_primary=False
        )

        open_count = {"n": 0}

        async def open_target(name: str):
            open_count["n"] += 1
            return extra_conn if name == "worker-1" else None

        ctx = ToolContext(
            primary=primary,
            extras={"worker-1": extra},
            open_target=open_target,
        )

        await ShellTool().run(
            ShellArgs(cmd="hostname", target="worker-1"), ctx
        )
        await ShellTool().run(
            ShellArgs(cmd="uptime", target="worker-1"), ctx
        )
        assert open_count["n"] == 1
        assert extra_conn.calls == ["hostname", "uptime"]

    @pytest.mark.asyncio
    async def test_open_target_failure_surfaces_as_tool_error(self):
        primary = ServerTarget(
            name="primary",
            server_id=1,
            ssh_conn=FakeConn("primary"),
            is_primary=True,
        )
        extra = ServerTarget(
            name="worker-1", server_id=2, ssh_conn=None, is_primary=False
        )

        async def open_target(_name: str):
            return None  # simulate connection failure

        ctx = ToolContext(
            primary=primary,
            extras={"worker-1": extra},
            open_target=open_target,
        )

        result = await ShellTool().run(
            ShellArgs(cmd="hostname", target="worker-1"), ctx
        )
        assert result.ok is False
        assert "unavailable" in result.error.lower()
        # Primary target should NOT have been called.
        assert primary.ssh_conn.calls == []

    @pytest.mark.asyncio
    async def test_unknown_target_never_invokes_open_target(self):
        primary = ServerTarget(
            name="primary",
            server_id=1,
            ssh_conn=FakeConn("primary"),
            is_primary=True,
        )
        opened: list[str] = []

        async def open_target(name: str):
            opened.append(name)
            return None

        ctx = ToolContext(
            primary=primary,
            extras={},  # nothing authorised
            open_target=open_target,
        )

        result = await ShellTool().run(
            ShellArgs(cmd="hostname", target="worker-1"), ctx
        )
        assert result.ok is False
        assert "unknown target" in result.error.lower()
        assert opened == []  # never reached open_target
