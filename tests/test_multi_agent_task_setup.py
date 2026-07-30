from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.agent_kernel.domain.roles import ROLE_SPECS
from app.agent_kernel.permissions.engine import PermissionEngine
from app.agent_kernel.tools.registry import ToolRegistry
from servers.agents.multi_agent_task_setup import (
    MultiAgentTaskRuntime,
    apply_task_runtime_metadata,
    build_task_recipe_query,
    build_task_recipe_scope,
    ensure_task_operational_recipes,
    prepare_multi_agent_task_runtime,
)


class FakeMemoryStore:
    def __init__(self):
        self.calls = []

    async def build_operational_recipes_prompt(self, query, *, server_ids, group_ids, limit):
        self.calls.append({"query": query, "server_ids": server_ids, "group_ids": group_ids, "limit": limit})
        return "recipe prompt"


def _runtime() -> MultiAgentTaskRuntime:
    return MultiAgentTaskRuntime(
        role_spec=ROLE_SPECS["log_investigator"],
        permission_engine=PermissionEngine(mode="PLAN", sudo_policy="never"),
        tool_registry=ToolRegistry({}),
        tool_names=["ssh_execute", "read_console"],
        max_iterations=5,
        title="Log Investigator",
    )


def test_apply_task_runtime_metadata_merges_existing_subagent_metadata():
    task = {"subagent": {"metadata": {"source": "planner"}, "role": "old"}}

    apply_task_runtime_metadata(task, _runtime())

    assert task["role"] == "log_investigator"
    assert task["permission_mode"] == "PLAN"
    assert task["max_iterations"] == 5
    assert task["tool_names"] == ["ssh_execute", "read_console"]
    assert task["subagent"] == {
        "metadata": {"source": "planner"},
        "role": "log_investigator",
        "title": "Log Investigator",
        "permission_mode": "PLAN",
        "tool_names": ["ssh_execute", "read_console"],
        "max_iterations": 5,
    }


def test_build_task_recipe_query_and_scope_are_deterministic():
    task = {"name": "Проверить логи nginx", "description": "Найти root cause"}
    servers = [
        SimpleNamespace(id=1, group_id=10),
        SimpleNamespace(id=2, group_id=10),
        SimpleNamespace(id=3, group_id=None),
        SimpleNamespace(id=4, group_id=20),
    ]

    query = build_task_recipe_query(task, ROLE_SPECS["log_investigator"])
    server_ids, group_ids = build_task_recipe_scope(servers, limit=3)

    assert "Проверить логи nginx" in query
    assert "Найти root cause" in query
    assert "logs" in query
    assert server_ids == [1, 2, 3]
    assert group_ids == [10]


@pytest.mark.asyncio
async def test_ensure_task_operational_recipes_loads_prompt_with_recipe_scope():
    task = {"name": "Проверить логи", "description": "Найти ошибки"}
    memory_store = FakeMemoryStore()
    servers = [SimpleNamespace(id=7, group_id=3), SimpleNamespace(id=8, group_id=3)]

    await ensure_task_operational_recipes(
        task,
        ROLE_SPECS["log_investigator"],
        memory_store=memory_store,
        servers=servers,
    )

    assert task["operational_recipes_prompt"] == "recipe prompt"
    assert memory_store.calls == [
        {
            "query": build_task_recipe_query(task, ROLE_SPECS["log_investigator"]),
            "server_ids": [7, 8],
            "group_ids": [3],
            "limit": 4,
        }
    ]


@pytest.mark.asyncio
async def test_ensure_task_operational_recipes_skips_existing_prompt():
    task = {"operational_recipes_prompt": "existing"}
    memory_store = FakeMemoryStore()

    await ensure_task_operational_recipes(
        task,
        ROLE_SPECS["custom"],
        memory_store=memory_store,
        servers=[],
    )

    assert task["operational_recipes_prompt"] == "existing"
    assert memory_store.calls == []


@pytest.mark.asyncio
async def test_prepare_multi_agent_task_runtime_returns_runtime_and_updates_task():
    task = {"name": "Логи", "description": "Проверить ошибки"}
    memory_store = FakeMemoryStore()
    task_subagent = {
        "role_spec": ROLE_SPECS["log_investigator"],
        "permission_engine": PermissionEngine(mode="PLAN", sudo_policy="never"),
        "tool_registry": ToolRegistry({}),
        "tool_names": ["read_console"],
        "max_iterations": 4,
        "title": "Log Investigator",
    }

    runtime = await prepare_multi_agent_task_runtime(
        task,
        task_subagent,
        memory_store=memory_store,
        servers=[SimpleNamespace(id=1, group_id=None)],
    )

    assert runtime.role_spec.slug == "log_investigator"
    assert runtime.tool_names == ["read_console"]
    assert task["role"] == "log_investigator"
    assert task["tool_names"] == ["read_console"]
    assert task["operational_recipes_prompt"] == "recipe prompt"
