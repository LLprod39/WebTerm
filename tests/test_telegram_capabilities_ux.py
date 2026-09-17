"""Telegram/web capability answers should stay human, not Studio registry dumps."""

from __future__ import annotations

import pytest
from django.contrib.auth.models import User

from app.assistant_actions import AssistantActionContext
from core_ui.models import ChatSession
from core_ui.services.assistant_chat_planning import _heuristic_plan
from core_ui.services.operator_channel import looks_like_tech_dump
from core_ui.services.operator_loop_prompt import (
    OPERATOR_CAPABILITIES_INTRO_RU,
    build_operator_system_prompt,
)
from studio.assistant_actions_inspect import capability_registry
from studio.models import MCPServerPool
from telegram_hub.assistant_bridge import _sanitize_telegram_assistant_reply


pytestmark = pytest.mark.django_db


def test_heuristic_what_can_you_do_returns_product_intro_without_registry():
    plan = _heuristic_plan("Что ты можешь ?")
    assert plan["actions"] == []
    assert plan["reply"] == OPERATOR_CAPABILITIES_INTRO_RU
    assert "id 4" not in plan["reply"]
    assert "[truncated]" not in plan["reply"]


def test_heuristic_explicit_studio_capabilities_still_calls_registry():
    plan = _heuristic_plan("Покажи реестр возможностей Studio")
    assert len(plan["actions"]) == 1
    assert plan["actions"][0]["action_type"] == "studio.capabilities.registry"


def test_heuristic_can_you_check_disk_is_not_capabilities_intro():
    plan = _heuristic_plan("можешь проверить диск на grafana")
    assert plan["reply"] != OPERATOR_CAPABILITIES_INTRO_RU
    assert not any(a.get("action_type") == "studio.capabilities.registry" for a in plan["actions"])


def test_telegram_prompt_includes_capabilities_intro_and_no_registry_rule():
    user = User.objects.create_user("tg-cap-prompt", password="x")
    session = ChatSession.objects.create(
        user=user,
        kind=ChatSession.KIND_TELEGRAM,
        title="tg",
        pinned_context={"channel": "telegram"},
    )
    prompt = build_operator_system_prompt(session)
    assert "Channel: telegram" in prompt or "# Telegram" in prompt
    assert "Studio registry" in prompt or "studio.capabilities.registry" in prompt or "MCP ids" in prompt
    assert OPERATOR_CAPABILITIES_INTRO_RU in prompt
    assert "Do not narrate" in prompt or "Never narrate" in prompt


def test_capability_registry_action_returns_chat_summary_not_full_dump():
    user = User.objects.create_user("cap-summary", password="x", is_staff=True)
    MCPServerPool.objects.create(
        owner=user,
        name="Kubernetes",
        description="kubectl cluster ops",
        transport=MCPServerPool.TRANSPORT_SSE,
        url="http://127.0.0.1:8771/mcp",
    )
    result = capability_registry(AssistantActionContext(user=user, input_payload={}))
    assert result["ui_table"] is False
    assert "reply_hint" in result
    assert "summary" in result
    assert "capability_registry" not in result
    assert result["summary"]["mcp_count"] >= 1
    assert "Kubernetes" in result["summary"]["mcp_names"]
    assert "Do NOT dump MCP ids" in result["reply_hint"]


def test_sanitize_replaces_registry_dump_with_intro():
    dump = (
        "Сейчас подтяну реестр возможностей Studio — по нему кратко расскажу, что умею."
        "Реестр возможностей получен (усечён). Добираю список MCP и skills."
        "Доступны 2 MCP: Kubernetes (id 4, kubectl, тест OK). Skills: frontend-ux-ui-structure …[truncated]"
    )
    assert looks_like_tech_dump(dump)
    text = _sanitize_telegram_assistant_reply(dump)
    assert "Цель:" in text
    assert "Оператор" in text
    assert "matching_mcp" not in text


def test_sanitize_keeps_normal_operator_reply():
    text = "14/16 healthy · 2 warning. Смотри алерт #12 на grafana."
    assert not looks_like_tech_dump(text)
    out = _sanitize_telegram_assistant_reply(text)
    assert "14/16 healthy" in out
    assert "Цель:" in out
