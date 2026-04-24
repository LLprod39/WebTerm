"""Tests for Terminal Agent tools (:mod:`servers.services.terminal_ai.agent.tools`).

Each tool is exercised through a fake SSH connection so we cover:
  - argument validation via pydantic schemas
  - target resolution (primary vs extras vs unknown)
  - safety vetos (shell), read-only guards, dry-run
  - success + error paths with structured output

The fake SSH connection captures the command string and returns a
configurable fake ``run()`` result.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from servers.services.terminal_ai.agent.tools import (
    AskUserArgs,
    AskUserOption,
    AskUserTool,
    DoneArgs,
    DoneTool,
    EditFileArgs,
    EditFileTool,
    GrepArgs,
    GrepTool,
    ListFilesArgs,
    ListFilesTool,
    ListTargetsArgs,
    ListTargetsTool,
    ReadFileArgs,
    ReadFileTool,
    ServerTarget,
    ShellArgs,
    ShellTool,
    TodoWriteArgs,
    TodoWriteTool,
    ToolContext,
    default_tool_set,
)

# ---------------------------------------------------------------------------
# Fixtures & helpers
# ---------------------------------------------------------------------------


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

    async def run(self, cmd: str, **_: Any) -> FakeRunResult:
        self.calls.append(cmd)
        for key, resp in self.responses.items():
            if key in cmd:
                return resp
        return self.default


def _primary_target(*, read_only: bool = False, ssh_conn: Any = None) -> ServerTarget:
    return ServerTarget(
        name="primary",
        server_id=1,
        display_name="srv-main",
        host="10.0.0.1",
        ssh_conn=ssh_conn or FakeSSHConn(),
        read_only=read_only,
        is_primary=True,
    )


def _ctx(**overrides: Any) -> ToolContext:
    return ToolContext(primary=_primary_target(), **overrides)


# ---------------------------------------------------------------------------
# ShellTool
# ---------------------------------------------------------------------------


class TestShellTool:
    @pytest.mark.asyncio
    async def test_runs_on_primary_by_default(self):
        conn = FakeSSHConn(default=FakeRunResult(stdout="ok\n", exit_status=0))
        ctx = ToolContext(primary=_primary_target(ssh_conn=conn))
        result = await ShellTool().run(ShellArgs(cmd="echo ok"), ctx)
        assert result.ok is True
        assert "Exit: 0" in result.output
        assert "ok" in result.output
        assert conn.calls == ["echo ok"]

    def test_rejects_empty_cmd_at_schema_level(self):
        """ShellArgs enforces min_length=1 so pydantic rejects before tool runs."""
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            ShellArgs(cmd="")

    @pytest.mark.asyncio
    async def test_rejects_multiline(self):
        ctx = _ctx()
        result = await ShellTool().run(ShellArgs(cmd="ls\nrm -rf /"), ctx)
        assert result.ok is False
        assert "multi-line" in result.error.lower()

    @pytest.mark.asyncio
    async def test_safety_blocks_dangerous(self):
        ctx = _ctx()
        # rm -rf / is in the default dangerous patterns
        result = await ShellTool().run(ShellArgs(cmd="rm -rf /"), ctx)
        assert result.ok is False
        assert "safety" in result.error.lower() or "safety" in result.output.lower()

    @pytest.mark.asyncio
    async def test_unknown_target_returns_error(self):
        ctx = _ctx()
        result = await ShellTool().run(
            ShellArgs(cmd="ls", target="nope"), ctx
        )
        assert result.ok is False
        assert "unknown target" in result.error.lower()

    @pytest.mark.asyncio
    async def test_dry_run_does_not_call_ssh(self):
        conn = FakeSSHConn()
        ctx = ToolContext(primary=_primary_target(ssh_conn=conn), dry_run=True)
        result = await ShellTool().run(ShellArgs(cmd="whoami"), ctx)
        assert result.ok is True
        assert "DRY-RUN" in result.output
        assert conn.calls == []  # no SSH call

    @pytest.mark.asyncio
    async def test_readonly_target_blocks_write(self):
        conn = FakeSSHConn()
        primary = _primary_target(read_only=True, ssh_conn=conn)
        ctx = ToolContext(primary=primary)
        result = await ShellTool().run(
            ShellArgs(cmd="echo hi > /tmp/x"), ctx
        )
        assert result.ok is False
        assert "read-only" in result.error.lower()
        assert conn.calls == []

    @pytest.mark.asyncio
    async def test_extra_target_routing(self):
        primary_conn = FakeSSHConn(default=FakeRunResult(stdout="P"))
        extra_conn = FakeSSHConn(default=FakeRunResult(stdout="E"))
        primary = _primary_target(ssh_conn=primary_conn)
        extra = ServerTarget(
            name="worker-1",
            server_id=2,
            display_name="srv-worker",
            ssh_conn=extra_conn,
            is_primary=False,
        )
        ctx = ToolContext(primary=primary, extras={"worker-1": extra})
        result = await ShellTool().run(
            ShellArgs(cmd="hostname", target="worker-1"), ctx
        )
        assert result.ok is True
        assert "E" in result.output
        assert extra_conn.calls == ["hostname"]
        assert primary_conn.calls == []  # untouched


# ---------------------------------------------------------------------------
# ReadFileTool
# ---------------------------------------------------------------------------


class TestReadFileTool:
    @pytest.mark.asyncio
    async def test_missing_file_error(self):
        conn = FakeSSHConn(default=FakeRunResult(stdout="STAT:MISSING MISSING\nDATA:"))
        ctx = ToolContext(primary=_primary_target(ssh_conn=conn))
        result = await ReadFileTool().run(ReadFileArgs(path="/etc/nope"), ctx)
        assert result.ok is False
        assert "not found" in result.error.lower()

    @pytest.mark.asyncio
    async def test_reads_and_decodes_base64(self):
        import base64

        content = "hello world\n"
        b64 = base64.b64encode(content.encode()).decode()
        conn = FakeSSHConn(default=FakeRunResult(stdout=f"STAT:12 1700000000\nDATA:{b64}"))
        ctx = ToolContext(primary=_primary_target(ssh_conn=conn))
        result = await ReadFileTool().run(ReadFileArgs(path="/etc/hostname"), ctx)
        assert result.ok is True
        assert "hello world" in result.output
        assert result.data["size"] == 12


# ---------------------------------------------------------------------------
# EditFileTool
# ---------------------------------------------------------------------------


class TestEditFileTool:
    @pytest.mark.asyncio
    async def test_refuses_missing_file_when_create_false(self):
        conn = FakeSSHConn(
            responses={"test -f": FakeRunResult(stdout="MISSING", exit_status=0)},
        )
        ctx = ToolContext(
            primary=_primary_target(ssh_conn=conn), user_id=1
        )
        result = await EditFileTool().run(
            EditFileArgs(path="/etc/new.conf", content="x=1"), ctx
        )
        assert result.ok is False
        assert "not found" in result.error.lower()

    @pytest.mark.asyncio
    async def test_readonly_target_refuses(self):
        conn = FakeSSHConn()
        ctx = ToolContext(
            primary=_primary_target(read_only=True, ssh_conn=conn), user_id=1
        )
        result = await EditFileTool().run(
            EditFileArgs(path="/etc/nginx.conf", content="x"), ctx
        )
        assert result.ok is False
        assert "read-only" in result.error.lower()
        assert conn.calls == []  # no SSH touched

    @pytest.mark.asyncio
    async def test_dry_run(self):
        conn = FakeSSHConn()
        ctx = ToolContext(
            primary=_primary_target(ssh_conn=conn), user_id=1, dry_run=True
        )
        result = await EditFileTool().run(
            EditFileArgs(path="/etc/hosts", content="x"), ctx
        )
        assert result.ok is True
        assert "DRY-RUN" in result.output
        assert conn.calls == []


# ---------------------------------------------------------------------------
# ListFilesTool
# ---------------------------------------------------------------------------


class TestListFilesTool:
    @pytest.mark.asyncio
    async def test_parses_ls_output(self):
        ls_stdout = (
            "total 12\n"
            "-rw-r--r-- 1 root root  120 1700000000 /etc/hosts\n"
            "drwxr-xr-x 2 root root 4096 1700000100 /etc/nginx\n"
        )
        conn = FakeSSHConn(default=FakeRunResult(stdout=ls_stdout, exit_status=0))
        ctx = ToolContext(primary=_primary_target(ssh_conn=conn))
        result = await ListFilesTool().run(ListFilesArgs(path="/etc"), ctx)
        assert result.ok is True
        entries = result.data["entries"]
        assert len(entries) == 2
        assert entries[0]["type"] == "file"
        assert entries[1]["type"] == "dir"


# ---------------------------------------------------------------------------
# GrepTool
# ---------------------------------------------------------------------------


class TestGrepTool:
    @pytest.mark.asyncio
    async def test_parses_matches(self):
        out = (
            "/etc/nginx/nginx.conf:42:    listen 443 ssl;\n"
            "/etc/nginx/sites-enabled/a.conf:7:    ssl_certificate /etc/ssl/a.pem;\n"
        )
        conn = FakeSSHConn(default=FakeRunResult(stdout=out, exit_status=0))
        ctx = ToolContext(primary=_primary_target(ssh_conn=conn))
        result = await GrepTool().run(
            GrepArgs(pattern="ssl", path="/etc/nginx"), ctx
        )
        assert result.ok is True
        assert len(result.data["matches"]) == 2
        assert result.data["matches"][0]["line"] == 42

    @pytest.mark.asyncio
    async def test_no_matches_returns_ok_empty(self):
        # grep returns exit 1 when nothing matches — still ok=True for us
        conn = FakeSSHConn(default=FakeRunResult(stdout="", exit_status=1))
        ctx = ToolContext(primary=_primary_target(ssh_conn=conn))
        result = await GrepTool().run(
            GrepArgs(pattern="nonexistent", path="/etc"), ctx
        )
        assert result.ok is True
        assert result.data["matches"] == []


# ---------------------------------------------------------------------------
# Meta tools
# ---------------------------------------------------------------------------


class TestListTargetsTool:
    @pytest.mark.asyncio
    async def test_shows_primary_and_extras(self):
        extra = ServerTarget(
            name="worker-1",
            server_id=2,
            display_name="srv-worker-1",
            is_primary=False,
            read_only=True,
        )
        ctx = ToolContext(primary=_primary_target(), extras={"worker-1": extra})
        result = await ListTargetsTool().run(ListTargetsArgs(), ctx)
        assert result.ok is True
        assert len(result.data["targets"]) == 2
        assert result.data["targets"][0]["is_primary"] is True
        assert result.data["targets"][1]["read_only"] is True


class TestTodoWriteTool:
    @pytest.mark.asyncio
    async def test_replaces_todos_and_emits_event(self):
        events: list[dict] = []

        async def emit(ev):
            events.append(ev)

        ctx = ToolContext(primary=_primary_target(), emit=emit)
        result = await TodoWriteTool().run(
            TodoWriteArgs(
                todos=[
                    {"id": "1", "content": "step 1", "status": "in_progress"},
                    {"id": "2", "content": "step 2", "status": "pending"},
                ]
            ),
            ctx,
        )
        assert result.ok is True
        assert len(ctx.todos) == 2
        assert ctx.todos[0]["status"] == "in_progress"
        assert any(e["type"] == "agent_todo_update" for e in events)


class TestAskUserTool:
    @pytest.mark.asyncio
    async def test_relays_reply(self):
        captured: list[object] = []

        async def prompt(request):
            captured.append(request)
            return "yes, proceed"

        ctx = ToolContext(primary=_primary_target(), prompt_user=prompt)
        result = await AskUserTool().run(
            AskUserArgs(question="Proceed?"), ctx
        )
        assert result.ok is True
        assert "yes, proceed" in result.output
        assert result.data["reply"] == "yes, proceed"
        assert len(captured) == 1
        assert captured[0].question == "Proceed?"
        assert captured[0].timeout_seconds == 300.0

    @pytest.mark.asyncio
    async def test_forwards_structured_options(self):
        captured: list[object] = []

        async def prompt(request):
            captured.append(request)
            return "да"

        ctx = ToolContext(primary=_primary_target(), prompt_user=prompt)
        result = await AskUserTool().run(
            AskUserArgs(
                question="Продолжить?",
                options=[
                    AskUserOption(label="Да", value="да"),
                    AskUserOption(label="Нет", value="нет", description="Остановить задачу"),
                ],
                allow_multiple=False,
                free_text_allowed=False,
                placeholder="Опишите решение",
            ),
            ctx,
        )
        assert result.ok is True
        assert len(captured) == 1
        assert [option.value for option in captured[0].options] == ["да", "нет"]
        assert captured[0].options[1].description == "Остановить задачу"
        assert captured[0].allow_multiple is False
        assert captured[0].free_text_allowed is False
        assert captured[0].placeholder == "Опишите решение"

    @pytest.mark.asyncio
    async def test_timeout_returns_error(self):
        async def prompt(request):
            return None

        ctx = ToolContext(primary=_primary_target(), prompt_user=prompt)
        result = await AskUserTool().run(
            AskUserArgs(question="Proceed?", timeout_seconds=5), ctx
        )
        assert result.ok is False
        assert "timeout" in result.error.lower()


class TestDoneTool:
    @pytest.mark.asyncio
    async def test_echoes_final_text(self):
        ctx = ToolContext(primary=_primary_target())
        result = await DoneTool().run(
            DoneArgs(final_text="All good."), ctx
        )
        assert result.ok is True
        assert "All good." in result.output


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


class TestRegistry:
    def test_default_tool_set_names(self):
        tools = default_tool_set()
        expected = {
            "shell",
            "read_file",
            "edit_file",
            "list_files",
            "grep",
            "list_targets",
            "ask_user",
            "todo_write",
            "remember",
            "done",
        }
        assert set(tools.keys()) == expected

    def test_tools_have_valid_args_schemas(self):
        tools = default_tool_set()
        for name, tool in tools.items():
            schema = tool.args_schema.model_json_schema()
            assert "properties" in schema or name == "done" or name == "list_targets"
