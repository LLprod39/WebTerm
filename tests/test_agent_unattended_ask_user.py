from __future__ import annotations

from types import SimpleNamespace

import pytest

from servers.agents.agent_engine_tools import execute_agent_tool
from servers.agents.multi_agent_task_runner import _ask_user_for_task


class _FakeRegistry:
    def get(self, name):
        return SimpleNamespace(name=name, input_schema={})


@pytest.mark.asyncio
async def test_unattended_ask_user_denied_in_react_tool_path():
    engine = SimpleNamespace(
        unattended=True,
        tool_registry=_FakeRegistry(),
        run_record=SimpleNamespace(pk=1),
        agent=SimpleNamespace(name="t"),
        user=None,
        permission_engine=SimpleNamespace(evaluate=lambda *a, **k: None),
        _policy_blocked_count=0,
        _validate_tool_args=lambda *a, **k: "",
        enabled_tools=["ask_user"],
        mcp_tools={},
        disabled_mcp_tools=set(),
        session=None,
        hook_manager=SimpleNamespace(post_tool_use=lambda n, t: t),
    )
    # bypass full path complexity: only unattended branch runs before registry for ask_user
    result = await execute_agent_tool(engine, "ask_user", {"question": "go?"})
    assert "unattended" in result.lower() or "Human input unavailable" in result
    assert engine._policy_blocked_count == 1


@pytest.mark.asyncio
async def test_unattended_ask_user_denied_in_multi_task_path():
    engine = SimpleNamespace(unattended=True, _policy_blocked_count=0, run_record=None)
    result = await _ask_user_for_task(engine, {"question": "need help?"})
    assert "Human input unavailable" in result
    assert engine._policy_blocked_count == 1
