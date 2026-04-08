from __future__ import annotations

from app.agent_kernel.domain.roles import RoleSpec
from app.agent_kernel.memory.redaction import sanitize_prompt_context_text


def build_ops_prompt_context(
    *,
    role_spec: RoleSpec,
    permission_mode: str,
    server_memory_prompt: str,
    operational_recipes_prompt: str = "",
    tool_registry_prompt: str,
    max_iterations: int,
    session_timeout: int,
) -> str:
    focus = ", ".join(role_spec.focus_areas)
    verification_rules = "\n".join(f"- {item}" for item in role_spec.verification_rules)
    safe_server_memory = sanitize_prompt_context_text(server_memory_prompt).text or "- Нет доступной памяти сервера"
    safe_operational_recipes = sanitize_prompt_context_text(operational_recipes_prompt).text or "- Нет релевантных operational recipes"
    safe_tool_registry = sanitize_prompt_context_text(tool_registry_prompt).text or "- Нет доступных инструментов"
    return f"""## Ops profile
Роль: {role_spec.title} ({role_spec.slug})
Permission mode: {permission_mode}
Фокус: {focus}
Бюджет: max_iterations={max_iterations}, session_timeout={session_timeout}s

## Role instructions
{role_spec.system_hint}

## Verification rules
{verification_rules}

## Operational recipes
{safe_operational_recipes}

## Tool registry slice
{safe_tool_registry}

## Server memory
{safe_server_memory}
"""
