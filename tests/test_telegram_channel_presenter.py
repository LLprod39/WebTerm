"""Telegram channel presenter / digest / prompt quality tests."""

from __future__ import annotations

import json

import pytest
from django.contrib.auth.models import User

from app.assistant_actions import AssistantActionContext
from core_ui.models import ChatMessage, ChatSession
from core_ui.services.operator_artifacts_inventory import compress_inventory_assistant_content
from core_ui.services.operator_channel import (
    build_telegram_digest,
    finalize_telegram_assistant_text,
    is_telegram_session,
    looks_like_tech_dump,
    pinned_context_for_history,
)
from core_ui.services.operator_loop_prompt import (
    OPERATOR_CAPABILITIES_INTRO_RU,
    build_operator_system_prompt,
)
from core_ui.services.operator_tools import truncate_tool_result
from studio.assistant_actions_inspect import list_mcp_servers, list_studio_skills
from studio.models import MCPServerPool
from telegram_hub.channel_presenter import (
    markdown_to_telegram_html,
    present_assistant_reply,
)


pytestmark = pytest.mark.django_db


def test_telegram_digest_lists_servers_from_metadata():
    meta = {
        "tables": [
            {
                "kind": "servers",
                "title": "Серверы · 3",
                "status_counts": {"healthy": 2, "warning": 1},
                "items": [
                    {"name": "api-prod-01", "host": "10.0.0.1", "port": 22, "status": "healthy"},
                    {"name": "bastion-01", "host": "10.0.0.2", "port": 22, "status": "warning"},
                    {"name": "grafana", "host": "10.0.0.3", "port": 22, "status": "healthy"},
                ],
            }
        ]
    }
    digest = build_telegram_digest(meta)
    assert "Серверы · 3" in digest
    assert "api-prod-01" in digest
    assert "bastion-01" in digest
    assert "🟡" in digest
    assert "🟢" in digest
    assert "10.0.0.1:22" in digest


def test_finalize_prefers_inventory_card_over_thin_summary():
    text = finalize_telegram_assistant_text(
        "Запрашиваю список серверов инвентаря. 18 серверов: 17 healthy, 1 unreachable (3 физических endpoint).",
        {
            "tables": [
                {
                    "kind": "servers",
                    "title": "Серверы · 3",
                    "note": "3 inventory rows map to 2 physical host:port endpoint(s).",
                    "status_counts": {"healthy": 2, "unreachable": 1},
                    "items": [
                        {"name": "lunix", "host": "79.1.2.3", "port": 22, "status": "unreachable"},
                        {"name": "api-prod-01", "host": "127.0.0.1", "port": 22, "status": "healthy"},
                        {"name": "bastion-01", "host": "10.0.0.2", "port": 22, "status": "healthy"},
                    ],
                }
            ]
        },
        user_message="Список серверов",
    )
    assert "Запрашиваю" not in text
    assert "Цель:" in text
    assert "lunix" in text
    assert "🔴" in text
    assert "api-prod-01" in text
    assert "1 unreachable" in text or "unreachable" in text
    assert "WebTerm" in text or "хост" in text.casefold()


def test_finalize_replaces_tech_dump_and_appends_digest():
    dump = (
        "Соберу актуальный список возможностей Studio. Реестр Studio: стратегия "
        "minimal_universal_nodes — agent/mcp_call. Ответ registry был обрезан …[truncated]"
    )
    assert looks_like_tech_dump(dump)
    text = finalize_telegram_assistant_text(
        dump,
        {
            "tables": [
                {
                    "kind": "servers",
                    "status_counts": {"healthy": 1},
                    "items": [{"name": "lunix", "status": "healthy"}],
                }
            ]
        },
    )
    assert "minimal_universal_nodes" not in text
    assert "lunix" in text


def test_finalize_replaces_bare_tech_dump_with_intro():
    dump = "Реестр возможностей Studio + matching_mcp + task_families …[truncated]"
    text = finalize_telegram_assistant_text(dump)
    assert "minimal_universal_nodes" not in text
    assert "Цель:" in text
    assert OPERATOR_CAPABILITIES_INTRO_RU.split(":")[0] in text or "Оператор" in text


def test_compress_inventory_skipped_for_telegram_session():
    user = User.objects.create_user("tg-compress", password="x")
    session = ChatSession.objects.create(
        user=user,
        kind=ChatSession.KIND_TELEGRAM,
        title="tg",
        pinned_context={"channel": "telegram"},
    )
    content = (
        "• api-prod-01 — API шлюз\n"
        "• bastion-01 — SSH прокси\n"
        "• stg-web-01 — staging окружение\n"
        "• ci-runner-01 — CI/CD\n"
    )
    msg = ChatMessage.objects.create(
        session=session,
        role=ChatMessage.ROLE_ASSISTANT,
        content=content,
        metadata={
            "tables": [
                {
                    "kind": "servers",
                    "status_counts": {"healthy": 4},
                    "items": [{"name": "api-prod-01"}, {"name": "bastion-01"}],
                }
            ],
            "inventory_card": True,
        },
    )
    assert is_telegram_session(session)
    assert compress_inventory_assistant_content(msg) is False
    msg.refresh_from_db()
    assert "API шлюз" in msg.content


def test_telegram_prompt_split_has_channel_rules_not_web_only_inventory():
    user = User.objects.create_user("tg-prompt-split", password="x")
    session = ChatSession.objects.create(
        user=user,
        kind=ChatSession.KIND_TELEGRAM,
        title="tg",
        pinned_context={"channel": "telegram", "bot_id": 1, "system_prompt": "secret bot"},
    )
    prompt = build_operator_system_prompt(session)
    assert "Channel: telegram" in prompt
    assert "# Telegram" in prompt
    assert "no Web UI cards" in prompt or "Telegram messenger" in prompt
    assert "# Web UI" in prompt
    assert OPERATOR_CAPABILITIES_INTRO_RU in prompt


def test_pinned_history_whitelist_for_telegram():
    pinned = {
        "channel": "telegram",
        "bot_id": 99,
        "telegram_user_id": 1,
        "chat_id": "1",
        "system_prompt": "do weird studio things",
        "servers": [{"id": 1, "name": "lunix"}],
    }
    out = pinned_context_for_history(pinned)
    assert out["channel"] == "telegram"
    assert out["servers"][0]["name"] == "lunix"
    assert "bot_id" not in out
    assert "system_prompt" not in out


def test_present_assistant_reply_builds_html_and_digest():
    messages = present_assistant_reply(
        content="16 серверов · все healthy.",
        metadata={
            "tables": [
                {
                    "kind": "servers",
                    "title": "Серверы · 2",
                    "status_counts": {"healthy": 2},
                    "items": [
                        {"name": "a-01", "host": "1.1.1.1", "port": 22, "status": "healthy"},
                        {"name": "b-01", "host": "1.1.1.2", "port": 22, "status": "healthy"},
                    ],
                }
            ]
        },
        actions=[],
        use_html=True,
    )
    assert messages
    assert messages[0].parse_mode == "HTML"
    body = messages[0].text
    assert "a-01" in body
    assert "<b>" in body or "Серверы" in body
    assert "🟢" in body


def test_markdown_to_telegram_html_basic():
    html = markdown_to_telegram_html("**bold** and `code` and [x](https://example.com)")
    assert "<b>bold</b>" in html
    assert "<code>code</code>" in html
    assert '<a href="https://example.com">x</a>' in html


def test_mcp_and_skills_list_return_summary_not_raw_ids():
    user = User.objects.create_user("mcp-sum", password="x", is_staff=True)
    MCPServerPool.objects.create(
        owner=user,
        name="Kubernetes",
        description="kubectl",
        transport=MCPServerPool.TRANSPORT_SSE,
        url="http://127.0.0.1:9/mcp",
    )
    mcp = list_mcp_servers(AssistantActionContext(user=user, input_payload={}))
    assert mcp["ui_table"] is False
    assert "summary" in mcp
    assert "Kubernetes" in mcp["summary"]["mcp_names"]
    assert "reply_hint" in mcp

    skills = list_studio_skills(AssistantActionContext(user=user, input_payload={}))
    assert skills["ui_table"] is False
    assert "summary" in skills
    assert "reply_hint" in skills


def test_truncate_prefers_summary_envelope():
    huge = {
        "ok": True,
        "result": {
            "ui_table": False,
            "reply_hint": "Summarize briefly.",
            "summary": {"mcp_count": 2, "mcp_names": ["A", "B"]},
            "mcp_servers": [{"id": i, "name": f"s{i}", "blob": "x" * 500} for i in range(40)],
        },
    }
    text = truncate_tool_result(huge, max_chars=800)
    assert "reply_hint" in text
    assert "summary" in text
    assert "…[truncated]" not in text or "mcp_count" in text
    payload = json.loads(text.split("…")[0] if text.endswith("…[rows omitted]") else text)
    # Accept either wrapped or unwrapped
    body = payload.get("result") if isinstance(payload.get("result"), dict) else payload
    assert body.get("summary", {}).get("mcp_count") == 2


def test_enqueue_telegram_delivery_only_for_telegram_sessions(monkeypatch):
    user = User.objects.create_user("tg-enqueue", password="x")
    web = ChatSession.objects.create(user=user, title="web")
    tg = ChatSession.objects.create(
        user=user,
        kind=ChatSession.KIND_TELEGRAM,
        title="tg",
        pinned_context={"channel": "telegram"},
    )
    called = []

    class FakeTask:
        @staticmethod
        def delay(*args, **kwargs):
            called.append((args, kwargs))

    monkeypatch.setattr("telegram_hub.tasks.telegram_deliver_assistant_message", FakeTask)
    from telegram_hub.assistant_bridge import enqueue_telegram_delivery_for_session

    assert enqueue_telegram_delivery_for_session(session_id=web.pk, assistant_message_id=1) is False
    assert called == []
    # Without binding still False
    assert enqueue_telegram_delivery_for_session(session_id=tg.pk, assistant_message_id=1) is False
