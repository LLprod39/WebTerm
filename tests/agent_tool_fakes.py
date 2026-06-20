from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from servers.services.terminal_ai.agent.tools import ServerTarget, ToolContext


@dataclass
class FakeRunResult:
    stdout: str = ""
    stderr: str = ""
    exit_status: int | None = 0


class FakeSSHConn:
    """Minimal asyncssh-alike for tool tests."""

    def __init__(self, responses: dict[str, FakeRunResult] | None = None, default: FakeRunResult | None = None):
        self.responses = responses or {}
        self.default = default or FakeRunResult(stdout="", stderr="", exit_status=0)
        self.calls: list[str] = []
        self.call_kwargs: list[dict[str, Any]] = []

    async def run(self, cmd: str, **kwargs: Any) -> FakeRunResult:
        self.calls.append(cmd)
        self.call_kwargs.append(dict(kwargs))
        for key, resp in self.responses.items():
            if key in cmd:
                return resp
        return self.default


def primary_target(*, read_only: bool = False, ssh_conn: Any = None) -> ServerTarget:
    return ServerTarget(
        name="primary",
        server_id=1,
        display_name="srv-main",
        host="10.0.0.1",
        ssh_conn=ssh_conn or FakeSSHConn(),
        read_only=read_only,
        is_primary=True,
    )


def tool_context(**overrides: Any) -> ToolContext:
    return ToolContext(primary=primary_target(), **overrides)
