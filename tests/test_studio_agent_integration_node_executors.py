from __future__ import annotations

from types import SimpleNamespace

import pytest
from asgiref.sync import async_to_sync

from servers.models import Server
from studio.models import MCPServerPool
from studio.pipeline.pipeline_executor import PipelineExecutor
from tests.studio_node_executor_harness import (
    HookManager,
    PermissionEngine,
    SandboxManager,
    disable_activity_logging,
    make_run,
)

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture(autouse=True)
def _disable_activity_logging(monkeypatch):
    disable_activity_logging(monkeypatch)


def test_ssh_cmd_node_runs_preflight_command_and_verification(monkeypatch):
    run = make_run("ssh-node-user")
    server = Server.objects.create(user=run.pipeline.owner, name="ssh-srv", host="10.0.0.3", username="root")
    calls: list[str] = []
    connect_kwargs_seen: dict[str, object] = {}

    class FakeConnection:
        async def run(self, command_text: str, timeout: int = 120):
            calls.append(command_text)
            return SimpleNamespace(stdout=f"ran {command_text}", stderr="", exit_status=0)

    class FakeConnectContext:
        async def __aenter__(self):
            return FakeConnection()

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

    async def fake_get_server_connect_kwargs(server_obj, *, connect_timeout=30):
        return {"host": server_obj.host, "username": server_obj.username, "connect_timeout": connect_timeout}

    async def fake_log_pipeline_ssh_command(*args, **kwargs):
        return None

    def fake_connect(**kwargs):
        connect_kwargs_seen.update(kwargs)
        return FakeConnectContext()

    monkeypatch.setattr("studio.pipeline.pipeline_agent_runtime.PermissionEngine", PermissionEngine)
    monkeypatch.setattr("studio.pipeline.pipeline_agent_runtime.SandboxManager", SandboxManager)
    monkeypatch.setattr("studio.pipeline.pipeline_agent_runtime.HookManager", HookManager)
    monkeypatch.setattr(
        "studio.pipeline.pipeline_agent_runtime._log_pipeline_ssh_command", fake_log_pipeline_ssh_command
    )
    monkeypatch.setattr(
        "studio.pipeline.pipeline_agent_runtime.get_server_connect_kwargs", fake_get_server_connect_kwargs
    )
    monkeypatch.setattr("asyncssh.connect", fake_connect)

    result = async_to_sync(PipelineExecutor(run)._execute_node)(
        {
            "id": "ssh",
            "type": "agent/ssh_cmd",
            "data": {
                "server_id_context_key": "target_server_id",
                "command": "echo {ticket}",
                "preflight_commands": ["echo preflight"],
                "verification_commands": ["echo verify"],
            },
        },
        {"ticket": "INC-55", "target_server_id": server.id},
        {},
    )

    assert result["status"] == "completed"
    assert result["exit_code"] == 0
    assert result["verification_summary"] == "verified"
    assert calls == ["echo preflight", "echo INC-55", "echo verify"]
    assert connect_kwargs_seen["connect_timeout"] == 30


def test_ssh_cmd_node_cannot_mutate_new_read_only_server():
    run = make_run("ssh-read-only-user")
    server = Server.objects.create(user=run.pipeline.owner, name="ssh-ro", host="10.0.0.4", username="root")

    result = async_to_sync(PipelineExecutor(run)._execute_node)(
        {
            "id": "ssh",
            "type": "agent/ssh_cmd",
            "data": {"server_id": server.id, "command": "mv /tmp/a /tmp/b"},
        },
        {},
        {},
    )

    assert result["status"] == "failed"
    assert "read-only" in result["error"]


def test_llm_query_node_streams_response_with_context(monkeypatch):
    run = make_run("llm-node-user")
    captured: dict[str, object] = {}

    async def fake_load_server_memory(owner, config, context):
        return "SERVER MEMORY"

    async def fake_load_operational_recipes(owner, config, context, *, role_slug, query):
        return "OPERATIONAL RECIPES"

    class FakeLLMProvider:
        async def stream_chat(self, full_prompt, *, model, specific_model=None, purpose, execution_context=None):
            captured["prompt"] = full_prompt
            captured["model"] = model
            captured["specific_model"] = specific_model
            captured["purpose"] = purpose
            captured["execution_context"] = execution_context
            for chunk in ["part-1 ", "part-2"]:
                yield chunk

    monkeypatch.setattr("studio.pipeline.pipeline_agent_llm._load_pipeline_server_memory", fake_load_server_memory)
    monkeypatch.setattr(
        "studio.pipeline.pipeline_agent_llm._load_pipeline_operational_recipes", fake_load_operational_recipes
    )
    monkeypatch.setattr("app.core.llm.LLMProvider", FakeLLMProvider)

    result = async_to_sync(PipelineExecutor(run)._execute_node)(
        {
            "id": "llm",
            "type": "agent/llm_query",
            "data": {
                "prompt": "Summarize incident {ticket}",
                "system_prompt": "SYSTEM",
                "provider": "gemini",
                "include_all_outputs": True,
            },
        },
        {"ticket": "INC-88"},
        {"prep": {"status": "completed", "output": "CPU at 99%"}},
    )

    assert result["status"] == "completed"
    assert result["output"] == "part-1 part-2"
    assert "Summarize incident INC-88" in str(captured["prompt"])
    assert "CPU at 99%" in str(captured["prompt"])
    assert "SERVER MEMORY" in str(captured["prompt"])
    assert captured["model"] == "gemini"
    assert captured["execution_context"] is not None


def test_mcp_call_node_executes_tool_and_tracks_execution(monkeypatch):
    run = make_run("mcp-node-user")
    mcp_server = MCPServerPool.objects.create(
        owner=run.pipeline.owner,
        name="Demo MCP",
        transport=MCPServerPool.TRANSPORT_SSE,
        url="http://localhost:8765/sse",
    )
    executor = PipelineExecutor(run)
    captured: dict[str, object] = {}

    async def fake_call_mcp_tool(server_obj, tool_name: str, arguments: dict):
        captured["server_name"] = server_obj.name
        captured["tool_name"] = tool_name
        captured["arguments"] = arguments
        return {"content": [{"type": "text", "text": "pong"}]}

    monkeypatch.setattr("studio.pipeline.pipeline_agent_mcp.PermissionEngine", PermissionEngine)
    monkeypatch.setattr("studio.pipeline.pipeline_agent_mcp.SandboxManager", SandboxManager)
    monkeypatch.setattr("studio.pipeline.pipeline_agent_mcp.HookManager", HookManager)
    monkeypatch.setattr("studio.pipeline.pipeline_agent_mcp.call_mcp_tool", fake_call_mcp_tool)

    result = async_to_sync(executor._execute_node)(
        {
            "id": "mcp",
            "type": "agent/mcp_call",
            "data": {
                "mcp_server_id": mcp_server.id,
                "tool_name": "ping",
                "arguments": {"ticket": "{ticket}"},
            },
        },
        {"ticket": "INC-101"},
        {},
    )

    assert result["status"] == "completed"
    assert "pong" in result["output"]
    assert captured["server_name"] == "Demo MCP"
    assert captured["tool_name"] == "ping"
    assert captured["arguments"] == {"ticket": "INC-101"}
    assert executor._executed_mcp_tools == {"ping"}
