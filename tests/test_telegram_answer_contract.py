"""Telegram answer contract: Цель/Статус/Детали/Дальше for any provider."""

from __future__ import annotations

import pytest
from django.contrib.auth.models import User

from app.assistant_actions import AssistantActionContext
from core_ui.models import ChatSession
from core_ui.services.operator_channel import (
    finalize_telegram_assistant_text,
    has_telegram_contract_anchors,
    wrap_telegram_answer_contract,
)
from core_ui.services.operator_loop_prompt import TELEGRAM_ANSWER_CONTRACT, build_operator_system_prompt
from core_ui.services.operator_tools import specs_to_tools
from servers.assistant_actions_agents import list_agents
from servers.operator.tools_playbooks import list_playbooks


pytestmark = pytest.mark.django_db


def test_telegram_prompt_includes_answer_contract():
    user = User.objects.create_user("tg-contract-prompt", password="x")
    session = ChatSession.objects.create(
        user=user,
        kind=ChatSession.KIND_TELEGRAM,
        title="tg",
        pinned_context={"channel": "telegram"},
    )
    prompt = build_operator_system_prompt(session)
    assert "# Telegram" in prompt
    assert "Telegram messenger" in prompt
    assert "Цель:" in prompt
    assert "Статус:" in prompt
    assert "Детали:" in prompt
    assert "Дальше:" in prompt
    assert TELEGRAM_ANSWER_CONTRACT[:40] in prompt


def test_wrap_adds_contract_anchors_to_freeform_prose():
    text = wrap_telegram_answer_contract(
        "Нашёл nikitavm и playbook Health check.",
        user_message="хелчек запусти на никитавм",
    )
    assert has_telegram_contract_anchors(text)
    assert "Цель:" in text
    assert "хелчек" in text.casefold() or "никитавм" in text.casefold()
    assert "Статус:" in text
    assert "Детали:" in text
    assert "Дальше:" in text


def test_finalize_enforces_contract_and_strips_truncated_narration():
    text = finalize_telegram_assistant_text(
        "Вот список playbooks (ответ обрезан)\n• Health check\n• Docker prune",
        user_message="Какие есть ansible?",
    )
    assert has_telegram_contract_anchors(text)
    assert "(ответ обрезан)" not in text.casefold()
    assert "Health check" in text


def test_present_awaiting_confirm_sets_status():
    text = finalize_telegram_assistant_text(
        "Готов запустить Health check на nikitavm.",
        user_message="запусти health check",
        awaiting_confirm=True,
    )
    assert has_telegram_contract_anchors(text)
    assert "ждёт подтверждения" in text.casefold()
    assert "Подтвердить" in text


@pytest.mark.django_db
def test_specs_to_tools_keeps_full_catalog_for_ansible_launch():
    user = User.objects.create_user("tg-full-tools", password="x", is_staff=True)
    tools = specs_to_tools(user, message="запусти ansible healthcheck на никитавм")
    types = {str(t.get("action_type")) for t in tools}
    assert "operator.list_playbooks" in types
    assert "operator.run_playbook" in types
    assert "web.search" in types or "agents.list" in types


def test_list_playbooks_returns_summary_n_of_m():
    user = User.objects.create_user("pb-sum", password="x", is_staff=True)
    result = list_playbooks(AssistantActionContext(user=user, input_payload={}, channel="telegram"))
    assert "summary" in result
    assert "total" in result["summary"]
    assert "shown" in result["summary"]
    assert result["shown"] == len(result["playbooks"])
    assert "reply_hint" not in result


def test_list_agents_returns_summary_cap():
    user = User.objects.create_user("ag-sum", password="x")
    result = list_agents(AssistantActionContext(user=user, input_payload={}, channel="telegram"))
    assert "summary" in result
    assert result["shown"] <= 12
    assert "reply_hint" not in result
