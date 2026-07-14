from __future__ import annotations

from typing import Any

from app.agent_kernel.domain.roles import ROLE_SPECS
from app.agent_kernel.permissions.engine import PermissionEngine
from app.agent_kernel.runtime.context import build_ops_prompt_context
from app.agent_kernel.runtime.subagents import build_task_subagent_spec
from app.agent_kernel.tools.registry import ToolRegistry
from servers.multi_agent_plan_helpers import make_task


def prepare_plan_tasks(
    tasks: list[dict],
    *,
    agent_type: str,
    parent_goal: str,
    tool_registry: ToolRegistry | None,
    max_task_iterations: int,
) -> list[dict]:
    if tool_registry is None:
        return [make_task(index, task["name"], task["description"]) for index, task in enumerate(tasks, start=1)]

    prepared_tasks: list[dict] = []
    for index, item in enumerate(tasks, start=1):
        # Prefer engine-level complex-task budget when the planner did not
        # pin a lower per-task max_iterations.
        requested_iters = item.get("max_iterations")
        if requested_iters is None:
            requested_iters = max_task_iterations
        subagent = build_task_subagent_spec(
            task_name=item["name"],
            task_description=item["description"],
            parent_agent_type=agent_type,
            parent_goal=parent_goal,
            tool_registry=tool_registry,
            requested_role=item.get("role"),
            requested_tool_names=item.get("tool_names"),
            requested_max_iterations=requested_iters,
            max_task_iterations_cap=max_task_iterations,
        )
        task = make_task(
            index,
            item["name"],
            item["description"],
            role=subagent.role,
            permission_mode=subagent.permission_mode,
            max_iterations=subagent.max_iterations,
            tool_names=list(subagent.tool_names),
        )
        task["subagent"] = {
            "role": subagent.role,
            "title": subagent.title,
            "permission_mode": subagent.permission_mode,
            "tool_names": list(subagent.tool_names),
            "allowed_categories": list(subagent.allowed_categories),
            "max_iterations": subagent.max_iterations,
            "metadata": dict(subagent.metadata),
        }
        prepared_tasks.append(task)
    return prepared_tasks


def build_task_subagent(
    task: dict,
    *,
    agent_type: str,
    parent_goal: str,
    fallback_role_spec: Any,
    parent_permission_engine: PermissionEngine,
    tool_registry: ToolRegistry | None,
    max_task_iterations: int,
) -> dict:
    if tool_registry is None:
        return {
            "role_spec": fallback_role_spec,
            "permission_engine": PermissionEngine(
                mode=fallback_role_spec.default_permission_mode,
                sudo_policy=parent_permission_engine.sudo_policy,
            ),
            "tool_registry": ToolRegistry({}),
            "tool_names": [],
            "max_iterations": max_task_iterations,
            "title": fallback_role_spec.title,
            "task": task,
        }

    requested_iters = task.get("max_iterations")
    if requested_iters is None:
        requested_iters = max_task_iterations
    spec = build_task_subagent_spec(
        task_name=task.get("name", ""),
        task_description=task.get("description", ""),
        parent_agent_type=agent_type,
        parent_goal=parent_goal,
        tool_registry=tool_registry,
        requested_role=task.get("role"),
        requested_tool_names=task.get("tool_names"),
        requested_max_iterations=requested_iters,
        max_task_iterations_cap=max_task_iterations,
    )
    role_spec = ROLE_SPECS.get(spec.role, fallback_role_spec)
    local_registry = tool_registry.subset(allowed_names=spec.tool_names)
    return {
        "role_spec": role_spec,
        "permission_engine": PermissionEngine(mode=spec.permission_mode, sudo_policy=parent_permission_engine.sudo_policy),
        "tool_registry": local_registry,
        "tool_names": list(spec.tool_names),
        "max_iterations": spec.max_iterations,
        "title": spec.title,
        "task": task,
    }


def build_subagent_prompt_context(
    task_subagent: dict,
    *,
    server_memory_prompt: str,
    operational_recipes_prompt: str,
    session_timeout: int,
) -> str:
    local_registry = task_subagent["tool_registry"]
    task = task_subagent.get("task") or {}
    return build_ops_prompt_context(
        role_spec=task_subagent["role_spec"],
        permission_mode=task_subagent["permission_engine"].mode,
        server_memory_prompt=server_memory_prompt or "- Память по серверам не загружена",
        operational_recipes_prompt=task.get("operational_recipes_prompt") or operational_recipes_prompt,
        tool_registry_prompt=local_registry.build_prompt_slice(limit=8),
        max_iterations=task_subagent["max_iterations"],
        session_timeout=session_timeout,
    )
