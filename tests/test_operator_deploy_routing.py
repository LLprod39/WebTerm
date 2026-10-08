"""Deploy/update helpers and full tool catalog (no keyword tool routing)."""

from __future__ import annotations

import pytest
from django.contrib.auth.models import User

from app.assistant_actions import AssistantActionContext, action_card_description, get_action_spec
from core_ui.services.assistant_chat_planning import _heuristic_plan
from core_ui.services.operator_loop_helpers import messages_have_deploy_mutating_tool
from core_ui.services.operator_loop_prompt import OPERATOR_SYSTEM_PROMPT, build_operator_system_prompt
from core_ui.services.operator_plan import approved_plan_step_matches
from core_ui.services.operator_tools import specs_to_tools
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


@pytest.mark.django_db
def test_specs_to_tools_returns_full_catalog_ignoring_message_keywords():
    user = User.objects.create_user("full-tools", password="x", is_staff=True)
    deploy_tools = specs_to_tools(user, message=DEPLOY_MSG)
    attach_tools = specs_to_tools(user, message=CONTRIBUTING_ATTACHMENT)
    empty_tools = specs_to_tools(user, message="")
    deploy_types = {str(t.get("action_type")) for t in deploy_tools}
    attach_types = {str(t.get("action_type")) for t in attach_tools}
    empty_types = {str(t.get("action_type")) for t in empty_tools}
    assert deploy_types == attach_types == empty_types
    assert "agent.create" in deploy_types
    assert "operator.create_playbook" in deploy_types
    assert "operator.todo_write" in deploy_types
    assert "operator.schedule_agent" in deploy_types


def test_operator_prompt_is_capability_map_not_keyword_scripts():
    prompt = build_operator_system_prompt(None)
    assert "operator.todo_write" in prompt
    assert "Capabilities map" in prompt or "Capabilities map" in OPERATOR_SYSTEM_PROMPT
    assert "Attached file contents" in prompt or "[Attached file contents]" in prompt
    assert "agent.create" in prompt
    # No hard "only when explicitly asked" gate that blocked typo'd create requests.
    assert "only when the operator explicitly asked" not in prompt.lower()


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
def test_list_playbooks_has_no_directive_reply_hint():
    user = User.objects.create_user("pb-hint", password="x", is_staff=True)
    result = list_playbooks(
        AssistantActionContext(user=user, input_payload={"q": "WebTerm"}, channel="web")
    )
    assert "reply_hint" not in result
    assert "summary" in result


@pytest.mark.django_db
def test_list_agents_has_no_directive_reply_hint():
    user = User.objects.create_user("ag-hint", password="x")
    result = list_agents(AssistantActionContext(user=user, input_payload={}, channel="web"))
    assert "reply_hint" not in result
    assert "summary" in result
