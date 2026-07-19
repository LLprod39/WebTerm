from __future__ import annotations

from app.agent_kernel.domain.roles import ROLE_SPECS, get_role_spec, resolve_task_role_slug
from app.agent_kernel.domain.specs import SubagentSpec
from app.agent_kernel.tools.registry import ToolRegistry


def build_task_subagent_spec(
    *,
    task_name: str,
    task_description: str,
    parent_agent_type: str,
    parent_goal: str,
    tool_registry: ToolRegistry,
    requested_role: str | None = None,
    requested_tool_names: list[str] | tuple[str, ...] | None = None,
    requested_max_iterations: int | None = None,
    max_task_iterations_cap: int | None = None,
) -> SubagentSpec:
    parent_role = get_role_spec(parent_agent_type, parent_goal)
    role_slug = requested_role if requested_role in ROLE_SPECS else resolve_task_role_slug(
        task_name,
        task_description,
        fallback_role=parent_role.slug,
    )
    role_spec = ROLE_SPECS[role_slug]

    scoped_registry = tool_registry.subset(allowed_categories=role_spec.allowed_tool_categories)
    if requested_tool_names:
        scoped_registry = scoped_registry.subset(allowed_names=requested_tool_names)
    if not scoped_registry.specs:
        scoped_registry = tool_registry.subset(allowed_names=["report", "ask_user"])

    # Engine cap may exceed role defaults so complex multi-step tasks can run
    # ~10–12 tool iterations; role defaults remain the floor preference when
    # no explicit request is provided.
    try:
        cap = int(max_task_iterations_cap) if max_task_iterations_cap is not None else int(role_spec.max_task_iterations)
    except (TypeError, ValueError):
        cap = int(role_spec.max_task_iterations)
    cap = max(1, cap)
    if requested_max_iterations is not None:
        try:
            requested = int(requested_max_iterations)
        except (TypeError, ValueError):
            requested = role_spec.max_task_iterations
        max_iterations = max(1, min(requested, cap))
    else:
        max_iterations = max(1, min(int(role_spec.max_task_iterations), cap))

    return SubagentSpec(
        role=role_spec.slug,
        title=role_spec.title,
        permission_mode=role_spec.default_permission_mode,
        tool_names=scoped_registry.names(),
        allowed_categories=tuple(role_spec.allowed_tool_categories),
        max_iterations=max_iterations,
        metadata={
            "focus_areas": list(role_spec.focus_areas),
            "verification_rules": list(role_spec.verification_rules),
        },
    )
