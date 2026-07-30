from __future__ import annotations

from app.agent_kernel.domain.roles import ROLE_SPECS
from servers.agents.multi_agent_task_prompts import build_multi_agent_task_prompt


class FakeMCPRuntimeProvider:
    def build_mcp_tools_description(self, bindings):
        return "MCP tools: " + ", ".join(sorted(bindings))


class FakeSkillProvider:
    def build_skill_catalog_description(self, skills):
        return "Skills: " + ", ".join(skill["slug"] for skill in skills)


def test_build_multi_agent_task_prompt_includes_task_context_and_materials():
    prompt = build_multi_agent_task_prompt(
        task={"name": "Проверить nginx", "description": "Собери статус сервиса"},
        role_spec=ROLE_SPECS["deploy_operator"],
        subagent_prompt_context="role/tool registry context",
        agent_input_artifacts=[
            {
                "kind": "document",
                "name": "Runbook",
                "content": "nginx should answer 200 on /health",
            }
        ],
        connected_servers=[{"server_name": "prod-web-1", "server_id": 12}],
        tool_names=["ssh_execute", "mcp_health_check"],
        mcp_runtime_provider=FakeMCPRuntimeProvider(),
        mcp_tools={
            "mcp_health_check": object(),
            "mcp_outside_slice": object(),
        },
        skill_provider=FakeSkillProvider(),
        skills=[{"slug": "nginx-ops"}],
        mcp_tool_errors=["broken mcp"],
        skill_errors=["missing skill"],
        sudo_policy="never",
        max_iterations=6,
        context_summary="Предыдущая задача нашла активный nginx",
    )

    assert prompt.history == [
        {"role": "system", "content": prompt.system_prompt},
        {"role": "user", "content": prompt.user_message},
    ]
    assert "Deploy Operator" in prompt.system_prompt
    assert "role/tool registry context" in prompt.system_prompt
    assert "nginx should answer 200 on /health" in prompt.system_prompt
    assert "- prod-web-1 (id: 12)" in prompt.system_prompt
    assert "ssh_execute" in prompt.system_prompt
    assert "MCP tools: mcp_health_check" in prompt.system_prompt
    assert "mcp_outside_slice" not in prompt.system_prompt
    assert "Skills: nginx-ops" in prompt.system_prompt
    assert "broken mcp" in prompt.system_prompt
    assert "missing skill" in prompt.system_prompt
    assert "Максимум 6 итераций" in prompt.system_prompt
    assert "Задача: Проверить nginx" in prompt.user_message
    assert "Контекст предыдущих задач" in prompt.user_message


def test_build_multi_agent_task_prompt_uses_empty_state_fallbacks():
    prompt = build_multi_agent_task_prompt(
        task={"name": "Inventory", "description": "List services"},
        role_spec=ROLE_SPECS["infra_scout"],
        subagent_prompt_context="registry context",
        agent_input_artifacts=[],
        connected_servers=[],
        tool_names=[],
        mcp_runtime_provider=None,
        mcp_tools={},
        skill_provider=None,
        skills=[],
        mcp_tool_errors=[],
        skill_errors=[],
        sudo_policy="never",
        max_iterations=4,
        context_summary="",
    )

    assert "- Нет активных SSH подключений" in prompt.system_prompt
    assert "- Skills не подключены" in prompt.system_prompt
    assert "Недоступные MCP подключения" not in prompt.system_prompt
    assert "Контекст предыдущих задач" not in prompt.user_message
