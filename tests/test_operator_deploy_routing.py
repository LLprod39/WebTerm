"""Deploy/update intent routing and attachment-safe deploy heuristics."""

from __future__ import annotations

import pytest
from django.contrib.auth.models import User

from app.assistant_actions import AssistantActionContext, action_card_description, get_action_spec
from core_ui.services.assistant_chat_planning import _heuristic_plan
from core_ui.services.operator_loop_helpers import messages_have_deploy_mutating_tool
from core_ui.services.operator_loop_prompt import OPERATOR_SYSTEM_PROMPT, build_operator_system_prompt
from core_ui.services.operator_plan import approved_plan_step_matches
from core_ui.services.operator_tools import _route_tools_for_message
from servers.assistant_actions_agents import list_agents
from servers.operator.tools_hints import (
    ATTACHED_FILE_CONTENTS_MARKER,
    strip_attachment_contents,
    user_wants_deploy_or_update,
)
from servers.operator.tools_playbooks import list_playbooks


DEPLOY_MSG = (
    "Обнови платформу на никита вм на эту версию "
    "https://github.com/LLprod39/WebTerm/tree/frontend-v3"
)

CONTRIBUTING_ATTACHMENT = f"""Посмотри этот файл

{ATTACHED_FILE_CONTENTS_MARKER}
# Contributing

## Branch workflow
Always create a feature branch from main.
Branch naming: frontend-v3
"""


def test_strip_attachment_contents():
    assert strip_attachment_contents(CONTRIBUTING_ATTACHMENT) == "Посмотри этот файл"
    assert user_wants_deploy_or_update(CONTRIBUTING_ATTACHMENT) is False
    assert user_wants_deploy_or_update(DEPLOY_MSG) is True
    assert user_wants_deploy_or_update("покажи список серверов") is False
    assert user_wants_deploy_or_update("задеплой frontend-v3 на nikitavm") is True


def test_user_wants_deploy_or_update_detects_russian_git_branch():
    assert user_wants_deploy_or_update(DEPLOY_MSG) is True
    assert user_wants_deploy_or_update("покажи список серверов") is False
    assert user_wants_deploy_or_update("задеплой frontend-v3 на nikitavm") is True


def test_route_tools_keeps_agent_create_for_explicit_deploy():
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


def test_route_tools_does_not_apply_deploy_routing_for_attachment_only():
    tools = [
        {"action_type": "agent.create", "name": "agent_create"},
        {"action_type": "operator.resolve_server", "name": "operator_resolve_server"},
        {"action_type": "operator.list_servers", "name": "operator_list_servers"},
        {"action_type": "web.search", "name": "web_search"},
    ]
    deploy_types = {str(t.get("action_type")) for t in _route_tools_for_message(tools, DEPLOY_MSG)}
    attach_types = {str(t.get("action_type")) for t in _route_tools_for_message(tools, CONTRIBUTING_ATTACHMENT)}
    assert "agent.create" in deploy_types
    assert "web.search" not in deploy_types
    assert "web.search" in attach_types


def test_operator_prompt_mentions_explicit_deploy_not_attachment_triggers():
    prompt = build_operator_system_prompt(None)
    assert "Обнови / задеплой" in prompt or "Обнови / задеплой" in OPERATOR_SYSTEM_PROMPT
    assert "Attached file contents" in prompt or "[Attached file contents]" in prompt
    assert "agent.create" in prompt


def test_heuristic_plan_proposes_agent_create_for_platform_update():
    plan = _heuristic_plan(DEPLOY_MSG)
    types = [a.get("action_type") for a in plan.get("actions") or []]
    assert "agent.create" in types
    assert "agents.list" not in types


def test_heuristic_plan_skips_agent_create_for_attachment_only_branch_text():
    plan = _heuristic_plan(CONTRIBUTING_ATTACHMENT)
    types = [a.get("action_type") for a in plan.get("actions") or []]
    assert "agent.create" not in types


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


def test_confirm_each_does_not_auto_run_agent_create_without_plan_step():
    plan = {
        "status": "approved",
        "steps": [
            {
                "id": 1,
                "text": "list",
                "tool": "agents.list",
                "input": {},
                "status": "pending",
            }
        ],
    }
    assert not approved_plan_step_matches(
        plan,
        action_type="agent.create",
        input_payload={"mode": "full", "goal": "x", "system_prompt": "y"},
    )


def test_action_card_description_agent_create_ru():
    spec = get_action_spec("agent.create")
    assert spec is not None
    assert "Создать агента" in action_card_description(spec, {"name": "Деплой WebTerm"})
    assert "задачи" in action_card_description(spec, {"goal": "Обновить платформу на сервере"})


def test_action_card_description_agent_run_ru():
    spec = get_action_spec("agent.run")
    assert spec is not None
    assert action_card_description(spec, {"agent_id": 42}) == "Запустить агента №42"


@pytest.mark.django_db
def test_list_playbooks_empty_hint_does_not_push_agent_create():
    user = User.objects.create_user("pb-empty-deploy", password="x", is_staff=True)
    result = list_playbooks(
        AssistantActionContext(user=user, input_payload={"q": "WebTerm"}, channel="web")
    )
    assert result["total"] == 0
    hint = str(result.get("reply_hint") or "").lower()
    assert "call agent.create" not in hint
    assert "then agent.run" not in hint


@pytest.mark.django_db
def test_list_agents_hint_does_not_push_agent_create():
    user = User.objects.create_user("ag-hint-deploy", password="x")
    result = list_agents(AssistantActionContext(user=user, input_payload={}, channel="web"))
    hint = str(result.get("reply_hint") or "").lower()
    assert "call agent.create" not in hint
    assert "then agent.run" not in hint
