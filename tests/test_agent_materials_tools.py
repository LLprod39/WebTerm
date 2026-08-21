from __future__ import annotations

import pytest
from django.test import override_settings

from servers.agents.agent_inputs import (
    build_agent_materials_prompt,
    get_material_by_ref,
    materials_catalog,
    normalize_input_artifacts,
)
from servers.agents.agent_sessions import AgentSessionManager
from servers.agents.agent_tools import (
    DEFAULT_READ_ONLY_AGENT_TOOLS,
    get_enabled_tools,
    tool_list_materials,
    tool_read_material,
    tool_run_script_material,
    tool_update_material_task,
)

SAMPLE_MATERIALS = [
    {
        "kind": "script",
        "name": "close-sbk.sh",
        "content": "#!/bin/bash\necho closing-sbk\nexit 0\n",
        "run_hint": "Run on target host then verify service",
    },
    {
        "kind": "task_list",
        "name": "SBK checklist",
        "tasks": [
            {"title": "Run close script", "details": "use operator script"},
            {"title": "Verify outcome", "details": "check logs/service"},
        ],
    },
    {
        "kind": "document",
        "name": "SOP",
        "content": "Step 1: prepare\nStep 2: close SBK\nStep 3: verify",
    },
]


def test_empty_tools_config_defaults_to_minimal_read_only_allowlist():
    enabled = get_enabled_tools({})

    assert set(enabled) == set(DEFAULT_READ_ONLY_AGENT_TOOLS)
    assert "ssh_execute" not in enabled
    assert "run_script_material" in enabled
    assert "read_material" in enabled
    assert "update_material_task" in enabled
    assert "send_ctrl_c" not in enabled


def test_normalize_assigns_ids_and_task_status():
    items = normalize_input_artifacts(SAMPLE_MATERIALS)
    assert len(items) == 3
    assert items[0]["id"] == "m1"
    assert items[0]["kind"] == "script"
    tasks = items[1]["tasks"]
    assert tasks[0]["status"] == "pending"
    assert get_material_by_ref(items, "close-sbk.sh")["kind"] == "script"
    catalog = materials_catalog(items)
    assert catalog[1]["tasks_open"] == 2


def test_materials_prompt_prefers_operator_scripts_and_tools():
    prompt = build_agent_materials_prompt(SAMPLE_MATERIALS)
    assert "run_script_material" in prompt
    assert "list_materials" in prompt
    assert "Не пиши свой скрипт" in prompt or "не пиши свой" in prompt.lower()
    assert "m1" in prompt
    assert "close-sbk.sh" in prompt


@pytest.mark.asyncio
async def test_list_read_update_and_run_script_tools():
    class _Server:
        id = 1
        name = "web-1"
        host = "10.0.0.1"

    session = AgentSessionManager(
        allowed_servers=[_Server()],
        available_materials=SAMPLE_MATERIALS,
    )
    session.execution_approval_granted = True
    # Pretend connected
    session.connections[1] = type(
        "S", (), {"server_id": 1, "server_name": "web-1", "proc": object(), "conn": object()}
    )()
    session._name_to_id["web-1"] = 1
    session._name_to_id["1"] = 1

    listed = await tool_list_materials(session)
    assert listed.success
    assert "m1" in listed.result

    read = await tool_read_material(session, material="m1")
    assert read.success
    assert "closing-sbk" in read.result or "echo" in read.result

    updated = await tool_update_material_task(
        session,
        material="m2",
        task_index=0,
        status="done",
        evidence="script exit 0",
    )
    assert updated.success
    assert '"status": "done"' in updated.result or '"done": true' in updated.result.replace(" ", "")

    async def fake_execute(server_id, command):
        assert server_id == 1
        assert "base64" in command
        # Decode what we would run: ensure script payload is present
        assert "WEBTERM_SCRIPT_EXIT" in command or "timeout" in command or "bash -n" in command
        return {"stdout": "closing-sbk\nWEBTERM_SCRIPT_EXIT=0\n", "stderr": "", "exit_code": 0, "duration_ms": 12}

    session.execute = fake_execute  # type: ignore[method-assign]

    ran = await tool_run_script_material(session, material="m1", server="web-1")
    assert ran.success
    assert ran.data.get("script_exit") == 0
    assert "run_script_material" in ran.result

    dry = await tool_run_script_material(session, material="m1", server="web-1", dry_run=True)
    assert dry.success
    assert dry.data.get("dry_run") is True


@pytest.mark.asyncio
async def test_run_script_material_is_blocked_by_server_read_only_policy():
    class _ReadOnlyServer:
        id = 1
        name = "readonly-1"
        host = "10.0.0.2"
        ai_read_only = True

    session = AgentSessionManager(
        allowed_servers=[_ReadOnlyServer()],
        available_materials=SAMPLE_MATERIALS,
    )
    session.connections[1] = type(
        "S", (), {"server_id": 1, "server_name": "readonly-1", "proc": object(), "conn": object()}
    )()
    session._name_to_id["readonly-1"] = 1
    called = False

    async def fake_execute(_server_id, _command):
        nonlocal called
        called = True
        raise AssertionError("read-only material execution reached SSH")

    session.execute = fake_execute  # type: ignore[method-assign]

    result = await tool_run_script_material(session, material="m1", server="readonly-1")

    assert result.success is False
    assert "read-only" in result.result
    assert called is False


@pytest.mark.asyncio
@override_settings(AGENT_MATERIAL_RUNNER_ENABLED=False)
async def test_run_script_material_without_server_fails_closed_off_backend_host():
    session = AgentSessionManager(allowed_servers=[], available_materials=SAMPLE_MATERIALS)
    session.execution_approval_granted = True

    result = await tool_run_script_material(session, material="m1")

    assert result.success is False
    assert result.data == {"code": "isolated_material_runner_unavailable", "runtime": "blocked"}
    assert "backend host" in result.result


@pytest.mark.asyncio
async def test_dangerous_material_is_blocked_when_dry_run_is_string_false():
    class _Server:
        id = 1
        name = "write-1"
        host = "10.0.0.3"
        ai_read_only = False

    materials = [{"kind": "script", "name": "danger.sh", "content": "#!/bin/bash\nrm -rf /\n"}]
    session = AgentSessionManager(allowed_servers=[_Server()], available_materials=materials)
    session.execution_approval_granted = True
    session.connections[1] = type(
        "S", (), {"server_id": 1, "server_name": "write-1", "proc": object(), "conn": object()}
    )()
    session._name_to_id["write-1"] = 1
    called = False

    async def fake_execute(_server_id, _command):
        nonlocal called
        called = True
        raise AssertionError("dangerous material reached SSH")

    session.execute = fake_execute  # type: ignore[method-assign]

    result = await tool_run_script_material(
        session,
        material="m1",
        server="write-1",
        dry_run="false",
    )

    assert result.success is False
    assert "high-risk" in result.result
    assert called is False
