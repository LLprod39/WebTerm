from __future__ import annotations

from types import SimpleNamespace

import pytest

import servers.agents.multi_agent_tool_execution as tool_execution
from app.agent_kernel.domain.specs import ToolSpec
from app.agent_kernel.permissions.engine import PermissionEngine
from app.agent_kernel.sandbox.manager import SandboxManager
from app.agent_kernel.tools.registry import ToolRegistry
from servers.agents.multi_agent_tool_execution import MultiAgentToolExecutionContext, execute_multi_agent_tool


class FakeHookManager:
    def __init__(self):
        self.calls: list[tuple[str, str]] = []

    async def post_tool_use(self, name: str, result: str) -> str:
        self.calls.append((name, result))
        return f"hooked:{name}:{result}"


def _context(**overrides) -> MultiAgentToolExecutionContext:
    values = {
        "session": object(),
        "permission_engine": PermissionEngine(mode="SAFE", sudo_policy="never"),
        "sandbox_manager": SandboxManager(),
        "hook_manager": FakeHookManager(),
        "tool_registry": None,
        "enabled_tools": [],
        "mcp_tools": {},
        "disabled_mcp_tools": set(),
        "skill_provider": None,
        "skill_policies": [],
        "executed_mcp_tools": set(),
        "mcp_runtime_provider": None,
    }
    values.update(overrides)
    return MultiAgentToolExecutionContext(**values)


def _ssh_spec() -> ToolSpec:
    return ToolSpec(
        name="ssh_execute",
        category="ssh",
        risk="exec",
        description="Execute shell command",
        input_schema={},
        requires_verification=True,
    )


@pytest.mark.asyncio
async def test_execute_multi_agent_tool_denies_tool_outside_subagent_slice():
    result = await execute_multi_agent_tool(
        "ssh_execute",
        {"server": "prod", "command": "systemctl status nginx"},
        context=_context(tool_registry=ToolRegistry({"ssh_execute": _ssh_spec()})),
        allowed_tool_names=["read_console"],
    )

    assert result == "Tool 'ssh_execute' is not available to this subagent."


@pytest.mark.asyncio
async def test_execute_multi_agent_tool_denies_missing_registry_spec():
    result = await execute_multi_agent_tool(
        "ssh_execute",
        {"server": "prod", "command": "systemctl status nginx"},
        context=_context(tool_registry=ToolRegistry({})),
    )

    assert result == "Tool 'ssh_execute' is not available in the current tool slice."


@pytest.mark.asyncio
async def test_execute_multi_agent_tool_builtin_path_runs_permission_sandbox_and_hook(monkeypatch):
    permission_engine = PermissionEngine(mode="SAFE", sudo_policy="never")
    hook_manager = FakeHookManager()
    session = object()
    seen = {}

    async def fake_ssh_execute(received_session, *, server: str, command: str, **_kw):
        seen["session"] = received_session
        seen["server"] = server
        seen["command"] = command
        return SimpleNamespace(success=True, result="nginx is active")

    monkeypatch.setattr(
        tool_execution,
        "get_all_agent_tools",
        lambda: {"ssh_execute": {"fn": fake_ssh_execute}},
    )

    result = await execute_multi_agent_tool(
        "ssh_execute",
        {"server": "prod", "command": "systemctl status nginx"},
        context=_context(
            session=session,
            permission_engine=permission_engine,
            hook_manager=hook_manager,
            tool_registry=ToolRegistry({"ssh_execute": _ssh_spec()}),
            enabled_tools=["ssh_execute"],
        ),
    )

    assert result == "hooked:ssh_execute:nginx is active"
    assert seen == {"session": session, "server": "prod", "command": "systemctl status nginx"}
    assert hook_manager.calls == [("ssh_execute", "nginx is active")]
    assert "service_preflight" in permission_engine.observed_markers
    assert "service_verification" in permission_engine.observed_markers


@pytest.mark.asyncio
async def test_execute_multi_agent_tool_disabled_builtin_keeps_legacy_message(monkeypatch):
    async def fake_ssh_execute(_session, **_kw):
        return SimpleNamespace(success=True, result="should not run")

    monkeypatch.setattr(
        tool_execution,
        "get_all_agent_tools",
        lambda: {"ssh_execute": {"fn": fake_ssh_execute}},
    )

    result = await execute_multi_agent_tool(
        "ssh_execute",
        {"server": "prod", "command": "systemctl status nginx"},
        context=_context(tool_registry=ToolRegistry({"ssh_execute": _ssh_spec()})),
    )

    assert result == "Tool 'ssh_execute' is disabled for this agent."
