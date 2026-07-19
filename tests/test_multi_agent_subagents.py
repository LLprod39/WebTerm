from __future__ import annotations

from app.agent_kernel.domain.roles import get_role_spec
from app.agent_kernel.domain.specs import ToolSpec
from app.agent_kernel.permissions.engine import PermissionEngine
from app.agent_kernel.tools.registry import ToolRegistry
from servers.multi_agent_subagents import (
    build_subagent_prompt_context,
    build_task_subagent,
    prepare_plan_tasks,
)


def _registry() -> ToolRegistry:
    return ToolRegistry(
        {
            "ssh_execute": ToolSpec(name="ssh_execute", category="ssh", risk="exec", description="ssh", input_schema={}),
            "read_console": ToolSpec(
                name="read_console",
                category="monitoring",
                risk="read",
                description="console",
                input_schema={},
            ),
            "keycloak_mutate": ToolSpec(
                name="keycloak_mutate",
                category="keycloak",
                risk="admin",
                description="kc",
                input_schema={},
            ),
        }
    )


def test_prepare_plan_tasks_without_registry_keeps_legacy_task_shape():
    tasks = prepare_plan_tasks(
        [{"name": "Проверить nginx", "description": "Собери статус"}],
        agent_type="custom",
        parent_goal="",
        tool_registry=None,
        max_task_iterations=7,
    )

    assert tasks[0]["id"] == 1
    assert tasks[0]["role"] == "custom"
    assert tasks[0]["permission_mode"] == "SAFE"
    assert tasks[0]["subagent"] == {}


def test_prepare_plan_tasks_with_registry_embeds_subagent_metadata_and_filters_tools():
    tasks = prepare_plan_tasks(
        [
            {
                "name": "Проверить журналы nginx",
                "description": "Собери logs и root cause",
                "tool_names": ["ssh_execute", "keycloak_mutate"],
                "max_iterations": 99,
            }
        ],
        agent_type="custom",
        parent_goal="",
        tool_registry=_registry(),
        max_task_iterations=7,
    )

    task = tasks[0]
    assert task["role"] == "log_investigator"
    assert task["subagent"]["role"] == "log_investigator"
    assert "ssh_execute" in task["tool_names"]
    assert "keycloak_mutate" not in task["tool_names"]
    # Engine cap (max_task_iterations=7) wins over role default and over inflated
    # requested max_iterations=99 — complex-task budget semantics.
    assert task["max_iterations"] == 7
    assert task["max_iterations"] == task["subagent"]["max_iterations"]


def test_build_task_subagent_prompt_context_uses_task_recipes_before_default():
    parent_permission = PermissionEngine(mode="SAFE", sudo_policy="never")
    task_subagent = build_task_subagent(
        {
            "name": "Проверить журналы nginx",
            "description": "Собери logs и root cause",
            "operational_recipes_prompt": "task specific recipe",
        },
        agent_type="custom",
        parent_goal="",
        fallback_role_spec=get_role_spec("custom"),
        parent_permission_engine=parent_permission,
        tool_registry=_registry(),
        max_task_iterations=7,
    )

    prompt = build_subagent_prompt_context(
        task_subagent,
        server_memory_prompt="server memory",
        operational_recipes_prompt="default recipe",
        session_timeout=900,
    )

    assert "task specific recipe" in prompt
    assert "default recipe" not in prompt
    assert "ssh_execute" in prompt
