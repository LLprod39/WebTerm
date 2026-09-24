"""Deploy/update intent must route to agent.create+run, not catalog-only."""

from __future__ import annotations

import pytest
from django.contrib.auth.models import User

from app.assistant_actions import AssistantActionContext
from core_ui.services.assistant_chat_planning import _heuristic_plan
from core_ui.services.operator_loop_helpers import messages_have_deploy_mutating_tool
from core_ui.services.operator_loop_prompt import OPERATOR_SYSTEM_PROMPT, build_operator_system_prompt
from core_ui.services.operator_tools import _route_tools_for_message
from servers.assistant_actions_agents import list_agents
from servers.operator.tools_hints import user_wants_deploy_or_update
from servers.operator.tools_playbooks import list_playbooks


DEPLOY_MSG = (
    "Обнови платформу на никита вм на эту версию "
    "https://github.com/LLprod39/WebTerm/tree/frontend-v3"
)


def test_user_wants_deploy_or_update_detects_russian_git_branch():
    assert user_wants_deploy_or_update(DEPLOY_MSG) is True
    assert user_wants_deploy_or_update("покажи список серверов") is False
    assert user_wants_deploy_or_update("задеплой frontend-v3 на nikitavm") is True


def test_route_tools_keeps_agent_create_for_deploy_without_word_agent():
    tools = [
        {"action_type": "agent.create", "name": "agent_create"},
        {"action_type": "agent.run", "name": "agent_run"},
        {"action_type": "agents.list", "name": "agents_list"},
        {"action_type": "operator.resolve_server", "name": "operator_resolve_server"},
        {"action_type": "operator.list_playbooks", "name": "operator_list_playbooks"},
        {"action_type": "web.search", "name": "web_search"},
    ]
    selected = _route_tools_for_message(tools, DEPLOY_MSG)
    types = {str(t.get("action_type")) for t in selected}
    assert "agent.create" in types
    assert "agent.run" in types
    assert "operator.resolve_server" in types
    assert "web.search" not in types


def test_operator_prompt_has_deploy_domain_rule():
    prompt = build_operator_system_prompt(None)
    assert "Обнови / задеплой" in prompt or "Обнови / задеплой" in OPERATOR_SYSTEM_PROMPT
    assert "agent.create" in prompt
    assert "НЕ останавливайся на «playbook не найден" in prompt or "playbook не найден" in prompt


def test_heuristic_plan_proposes_agent_create_for_platform_update():
    plan = _heuristic_plan(DEPLOY_MSG)
    types = [a.get("action_type") for a in plan.get("actions") or []]
    assert "agent.create" in types
    assert "agents.list" not in types


def test_messages_have_deploy_mutating_tool_detects_create():
    assert messages_have_deploy_mutating_tool(
        [
            {
                "role": "assistant",
                "content": [
                    {"type": "tool_use", "id": "1", "name": "agent_create", "input": {"mode": "full"}},
                ],
            }
        ]
    )
    assert not messages_have_deploy_mutating_tool(
        [
            {
                "role": "assistant",
                "content": [
                    {"type": "tool_use", "id": "1", "name": "agents_list", "input": {}},
                ],
            }
        ]
    )


@pytest.mark.django_db
def test_list_playbooks_empty_hint_pushes_agent_create():
    user = User.objects.create_user("pb-empty-deploy", password="x", is_staff=True)
    result = list_playbooks(
        AssistantActionContext(user=user, input_payload={"q": "WebTerm"}, channel="web")
    )
    assert result["total"] == 0
    hint = str(result.get("reply_hint") or "")
    assert "agent.create" in hint
    assert "agent.run" in hint


@pytest.mark.django_db
def test_list_agents_hint_mentions_create_when_deploy_mismatch():
    user = User.objects.create_user("ag-hint-deploy", password="x")
    result = list_agents(AssistantActionContext(user=user, input_payload={}, channel="web"))
    hint = str(result.get("reply_hint") or "")
    assert "agent.create" in hint
