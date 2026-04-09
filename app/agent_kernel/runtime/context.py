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
    memory_warmup_prompt: str = "",
) -> str:
    """
    Строит блок системного контекста для ops-агента.

    ``memory_warmup_prompt`` (GAP 5) — опциональный блок из последних N AgentRun,
    который вставляется перед основной памятью сервера. Позволяет агенту учитывать
    историю предыдущих запусков без дублирования полного memory card.
    """
    focus = ", ".join(role_spec.focus_areas)
    verification_rules = "\n".join(f"- {item}" for item in role_spec.verification_rules)
    safe_server_memory = sanitize_prompt_context_text(server_memory_prompt).text or "- Нет доступной памяти сервера"
    safe_operational_recipes = sanitize_prompt_context_text(operational_recipes_prompt).text or "- Нет релевантных operational recipes"
    safe_tool_registry = sanitize_prompt_context_text(tool_registry_prompt).text or "- Нет доступных инструментов"
    safe_warmup = sanitize_prompt_context_text(memory_warmup_prompt).text if memory_warmup_prompt else ""

    warmup_section = ""
    if safe_warmup:
        warmup_section = f"\n## Recent agent history\n{safe_warmup}\n"

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
{warmup_section}
## Server memory
{safe_server_memory}
"""
