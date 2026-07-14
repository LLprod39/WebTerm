from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.agent_kernel.domain.roles import RoleSpec
from app.agent_kernel.domain.specs import MCPRuntimeProvider, SkillProvider
from app.agent_kernel.mcp_runtime import describe_mcp_bindings
from app.sudo_policy import sudo_policy_prompt
from servers.agent_inputs import build_agent_materials_prompt
from servers.agent_tools import get_tools_description


@dataclass(frozen=True)
class MultiAgentTaskPrompt:
    system_prompt: str
    user_message: str
    history: list[dict[str, str]]


def build_multi_agent_task_prompt(
    *,
    task: dict[str, Any],
    role_spec: RoleSpec,
    subagent_prompt_context: str,
    agent_input_artifacts: Any,
    connected_servers: list[dict[str, Any]],
    tool_names: list[str],
    mcp_runtime_provider: MCPRuntimeProvider | None,
    mcp_tools: dict[str, Any],
    skill_provider: SkillProvider | None,
    skills: list[Any],
    mcp_tool_errors: list[str],
    skill_errors: list[str],
    sudo_policy: Any,
    max_iterations: int,
    context_summary: str,
) -> MultiAgentTaskPrompt:
    servers_desc = _describe_connected_servers(connected_servers)
    tools_desc = _describe_available_tools(
        tool_names=tool_names,
        mcp_runtime_provider=mcp_runtime_provider,
        mcp_tools=mcp_tools,
    )
    skills_desc = skill_provider.build_skill_catalog_description(skills) if skill_provider else ""
    materials_prompt = build_agent_materials_prompt(agent_input_artifacts)
    system_prompt = f"""Ты — subagent роли {role_spec.title}, выполняющий одну конкретную задачу внутри orchestrated DevOps pipeline.
Работай только в пределах своей роли, permission mode и выданного tool slice. Отвечай на русском языке.

{subagent_prompt_context}
{materials_prompt}

Подключённые серверы:
{servers_desc}

Attached skills:
{skills_desc or "- Skills не подключены"}

Доступные инструменты:
{tools_desc}
{_format_error_list("Недоступные MCP подключения", mcp_tool_errors)}
{_format_error_list("Недоступные skills", skill_errors)}

Формат вывода на каждом шаге:
THOUGHT: <рассуждение>
ACTION: tool_name {{"param1": "val1"}}

Альтернатива JSON:
{{"thinking": "<рассуждение>", "tool": "tool_name", "args": {{"param1": "val1"}}}}

Если attached skills релевантны задаче, сначала открой нужный skill через read_skill перед сервис-специфичными изменениями.
Если attached skills содержат runtime guardrails, соблюдай их как обязательные ограничения.
Нельзя вызывать инструменты вне выданного tool slice.
{sudo_policy_prompt(sudo_policy)}

Когда задача выполнена — напиши итоговый вывод БЕЗ строки ACTION.
Если перед этим были изменения, но verification markers не закрыты, ты ОБЯЗАН продолжить выполнение и провести post-change verification.
Максимум {max_iterations} итераций."""

    context_block = f"\n\nКонтекст предыдущих задач:\n{context_summary}" if context_summary.strip() else ""
    user_message = f"Задача: {task['name']}\n{task['description']}{context_block}"
    return MultiAgentTaskPrompt(
        system_prompt=system_prompt,
        user_message=user_message,
        history=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
    )


def _describe_connected_servers(connected_servers: list[dict[str, Any]]) -> str:
    return (
        "\n".join(f"- {item['server_name']} (id: {item['server_id']})" for item in connected_servers)
        or "- Нет активных SSH подключений"
    )


def _describe_available_tools(
    *,
    tool_names: list[str],
    mcp_runtime_provider: MCPRuntimeProvider | None,
    mcp_tools: dict[str, Any],
) -> str:
    tools_desc = get_tools_description(tool_names)
    local_mcp_tools = {name: binding for name, binding in mcp_tools.items() if name in tool_names}
    mcp_tools_desc = describe_mcp_bindings(mcp_runtime_provider, local_mcp_tools)
    if mcp_tools_desc:
        return f"{tools_desc}\n\n{mcp_tools_desc}" if tools_desc else mcp_tools_desc
    return tools_desc


def _format_error_list(title: str, errors: list[str]) -> str:
    if not errors:
        return ""
    return f"\n{title}:\n" + "\n".join(f"- {item}" for item in errors)
