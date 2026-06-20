from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.agent_kernel.domain.roles import RoleSpec
from app.agent_kernel.permissions.engine import PermissionEngine
from app.agent_kernel.tools.registry import ToolRegistry


@dataclass(frozen=True)
class MultiAgentTaskRuntime:
    role_spec: RoleSpec
    permission_engine: PermissionEngine
    tool_registry: ToolRegistry
    tool_names: list[str]
    max_iterations: int
    title: str


async def prepare_multi_agent_task_runtime(
    task: dict[str, Any],
    task_subagent: dict[str, Any],
    *,
    memory_store: Any,
    servers: list[Any],
) -> MultiAgentTaskRuntime:
    runtime = MultiAgentTaskRuntime(
        role_spec=task_subagent["role_spec"],
        permission_engine=task_subagent["permission_engine"],
        tool_registry=task_subagent["tool_registry"],
        tool_names=list(task_subagent["tool_names"]),
        max_iterations=task_subagent["max_iterations"],
        title=task_subagent["title"],
    )
    apply_task_runtime_metadata(task, runtime)
    await ensure_task_operational_recipes(task, runtime.role_spec, memory_store=memory_store, servers=servers)
    return runtime


def apply_task_runtime_metadata(task: dict[str, Any], runtime: MultiAgentTaskRuntime) -> None:
    task["role"] = runtime.role_spec.slug
    task["permission_mode"] = runtime.permission_engine.mode
    task["max_iterations"] = runtime.max_iterations
    task["tool_names"] = list(runtime.tool_names)
    task["subagent"] = {
        **(task.get("subagent") or {}),
        "role": runtime.role_spec.slug,
        "title": runtime.title,
        "permission_mode": runtime.permission_engine.mode,
        "tool_names": list(runtime.tool_names),
        "max_iterations": runtime.max_iterations,
    }


async def ensure_task_operational_recipes(
    task: dict[str, Any],
    role_spec: RoleSpec,
    *,
    memory_store: Any,
    servers: list[Any],
    server_limit: int = 3,
    recipe_limit: int = 4,
) -> None:
    if task.get("operational_recipes_prompt"):
        return

    server_ids, group_ids = build_task_recipe_scope(servers, limit=server_limit)
    task["operational_recipes_prompt"] = await memory_store.build_operational_recipes_prompt(
        build_task_recipe_query(task, role_spec),
        server_ids=server_ids,
        group_ids=group_ids,
        limit=recipe_limit,
    )


def build_task_recipe_query(task: dict[str, Any], role_spec: RoleSpec) -> str:
    return "\n".join(
        part for part in [task.get("name") or "", task.get("description") or "", *role_spec.focus_areas] if part
    )


def build_task_recipe_scope(servers: list[Any], *, limit: int = 3) -> tuple[list[int], list[int]]:
    scoped_servers = servers[:limit]
    server_ids = [server.id for server in scoped_servers]
    group_ids = [server.group_id for server in scoped_servers if getattr(server, "group_id", None)]
    return server_ids, list(dict.fromkeys(group_ids))
