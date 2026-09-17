"""Residual Telegram Confirm / resume / ansible-facts fixes."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from django.contrib.auth.models import User

from core_ui.managed_secrets import set_telegram_bot_token
from core_ui.models import AssistantAction, ChatSession
from core_ui.services.assistant_confirm import resume_operator_if_parked
from servers.services.playbook_compatibility_analysis import (
    analyze_playbook_compatibility,
    is_gatherable_ansible_fact,
    is_user_required_runtime_variable,
)
from studio.telegram_delivery_service import telegram_bot_token_digest
from telegram_hub.assistant_bridge import (
    _outcome_to_telegram_result,
    _user_facing_resume_error,
    is_missing_runtime_vars_error,
    missing_runtime_variables_from_action,
    peek_playbook_vars_pending,
)
from telegram_hub.models import TelegramAccountLink, TelegramBot

pytestmark = pytest.mark.django_db(transaction=True)


def test_resume_always_runs_in_fresh_thread(monkeypatch):
    seen = {"threads": set()}

    async def fake_resume(*, action, request=None, cancelled=False):
        import threading

        seen["threads"].add(threading.current_thread().name)
        return SimpleNamespace(ok=True)

    monkeypatch.setattr("core_ui.services.operator_loop.resume_after_action", fake_resume)

    user = User.objects.create_user("resume-thread", password="x")
    session = ChatSession.objects.create(user=user, title="t")
    action = AssistantAction.objects.create(
        user=user,
        session=session,
        action_type="operator.run_playbook",
        status=AssistantAction.STATUS_COMPLETED,
        risk=AssistantAction.RISK_MUTATING,
    )

    import threading

    caller = threading.current_thread().name
    result, err = resume_operator_if_parked(action)
    assert err is None
    assert result is not None
    assert seen["threads"]
    assert caller not in seen["threads"]


def test_gatherable_ansible_facts_helpers():
    assert is_gatherable_ansible_fact("ansible_hostname")
    assert is_gatherable_ansible_fact("ansible_memtotal_mb")
    assert is_gatherable_ansible_fact("ansible_facts.os_family")
    assert not is_gatherable_ansible_fact("ansible_password")
    assert not is_gatherable_ansible_fact("my_app_token")
    assert is_user_required_runtime_variable("my_app_token")
    assert not is_user_required_runtime_variable("ansible_hostname")


def test_compatibility_facts_not_required_custom_vars_are():
    facts_yaml = """
- hosts: all
  gather_facts: true
  tasks:
    - name: show
      ansible.builtin.debug:
        msg: "{{ ansible_hostname }} {{ ansible_memtotal_mb }} {{ ansible_distribution }}"
"""
    report = analyze_playbook_compatibility(facts_yaml)
    assert "ansible_hostname" not in (report.get("required_variables") or [])
    assert "ansible_memtotal_mb" not in (report.get("required_variables") or [])
    assert any(issue.get("code") == "gathered_facts_referenced" for issue in report.get("issues") or [])

    custom_yaml = """
- hosts: all
  tasks:
    - name: use secret
      ansible.builtin.debug:
        msg: "{{ my_app_token }} {{ db_password }}"
"""
    report2 = analyze_playbook_compatibility(custom_yaml)
    required = set(report2.get("required_variables") or [])
    assert "my_app_token" in required
    assert "db_password" in required


def test_compatibility_report_does_not_block_on_facts_only():
    from servers.services.playbook_compatibility_analysis import is_user_required_runtime_variable

    required = ["ansible_hostname", "ansible_memtotal_mb", "my_app_token"]
    missing = [name for name in required if is_user_required_runtime_variable(name)]
    assert missing == ["my_app_token"]


def test_telegram_wizard_skips_ansible_facts_only():
    user = User.objects.create_user("tg-facts", password="x")
    bot = TelegramBot.objects.create(
        kind=TelegramBot.KIND_PLATFORM,
        name="Platform",
        token_digest=telegram_bot_token_digest("facts-token"),
        is_active=True,
        mode=TelegramBot.MODE_ASSISTANT,
    )
    set_telegram_bot_token(bot.pk, "facts-token")
    link = TelegramAccountLink.objects.create(
        user=user,
        bot=bot,
        telegram_user_id=999,
        chat_id="999",
        status=TelegramAccountLink.STATUS_LINKED,
    )
    session = ChatSession.objects.create(user=user, title="tg", kind=ChatSession.KIND_TELEGRAM)
    action = AssistantAction.objects.create(
        user=user,
        session=session,
        action_type="operator.run_playbook",
        status=AssistantAction.STATUS_FAILED,
        risk=AssistantAction.RISK_MUTATING,
        error="Provide every required runtime variable before running",
        result_payload={
            "compatibility": {
                "missing_runtime_variables": [
                    "ansible_hostname",
                    "ansible_memtotal_mb",
                    "ansible_distribution",
                ]
            }
        },
        input_payload={"playbook_id": 38, "server_ids": [33]},
    )
    assert missing_runtime_variables_from_action(action) == []
    assert is_missing_runtime_vars_error(action) is False

    outcome = SimpleNamespace(
        action=action,
        resume=None,
        resume_error="Single thread executor already being used, would deadlock",
        stale_cleared=True,
    )
    result = _outcome_to_telegram_result(outcome=outcome, link=link)
    assert peek_playbook_vars_pending(link.pk) is None
    assert not any("Ожидаются:" in line for line in result.chat_lines)
    assert any("Не удалось продолжить диалог" in line for line in result.chat_lines)
    assert "Single thread executor" not in "\n".join(result.chat_lines)


def test_user_facing_resume_error_softens_deadlock():
    msg = _user_facing_resume_error("Single thread executor already being used, would deadlock")
    assert "Single thread" not in msg
    assert "диалог" in msg.lower()


def test_normalize_host_hint_transliterates_cyrillic():
    from servers.operator.tools_hints import normalize_host_hint, server_matches_query, transliterate_cyrillic

    assert transliterate_cyrillic("никитавм") == "nikitavm"
    assert normalize_host_hint("никитавм") == "nikitavm"

    server = SimpleNamespace(id=33, name="nikitavm", host="79.100.193.234", tags="")
    assert server_matches_query(server, "никитавм") is True
    assert server_matches_query(server, "nikitavm") is True
