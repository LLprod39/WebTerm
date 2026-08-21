import pytest
from asgiref.sync import async_to_sync
from django.contrib.auth.models import User

from core_ui.models import ChatMessage, ChatSession
from core_ui.services.operator_loop_helpers import (
    _ensure_visible_answer,
    _fallback_answer_from_metadata,
    _is_card_placeholder,
)
from core_ui.services.operator_loop_prompt import OPERATOR_SYSTEM_PROMPT


def _metrics() -> dict:
    return {
        "name": "web-01",
        "status": "healthy",
        "cpu_percent": 31,
        "mem_percent": 64,
        "disk_percent": 72,
        "disk_mounts": [{"mount": "/data", "percent": 81}],
    }


def _alerts() -> dict:
    return {
        "kind": "alerts",
        "items": [
            {
                "id": 7,
                "server_name": "db-01",
                "severity": "critical",
                "title": "Disk usage 94%",
            },
            {
                "id": 8,
                "server_name": "web-01",
                "severity": "warning",
                "title": "High memory",
            },
        ],
    }


def test_metrics_fallback_is_a_grounded_report_not_a_card_pointer():
    answer = _fallback_answer_from_metadata({"metrics": _metrics()})

    assert "web-01" in answer
    assert "CPU 31%" in answer
    assert "RAM 64%" in answer
    assert "диск /data 81%" in answer
    assert "проверь динамику" in answer
    assert "карточ" not in answer.lower()


def test_alerts_fallback_prioritizes_real_severity_and_next_action():
    answer = _fallback_answer_from_metadata({"tables": [_alerts()]})

    assert "Открыто 2 алерта" in answer
    assert "1 critical" in answer
    assert "db-01: Disk usage 94%" in answer
    assert "Сначала разбери critical/high" in answer
    assert "список ниже" not in answer.lower()


def test_combined_report_summarizes_metrics_and_alerts_without_duplication():
    answer = _fallback_answer_from_metadata({"metrics": _metrics(), "tables": [_alerts()]})

    assert answer.count("web-01: CPU") == 1
    assert answer.count("Открыто 2 алерта") == 1
    assert answer.count("Дальше:") == 1
    assert "карточ" not in answer.lower()


def test_combined_report_calls_out_freshness_conflict_between_metrics_and_alerts():
    alerts = _alerts()
    alerts["items"][0]["title"] = "Server unreachable"

    answer = _fallback_answer_from_metadata({"metrics": _metrics(), "tables": [alerts]})

    assert "Есть расхождение" in answer
    assert "Сверь время и источник" in answer


def test_empty_forecast_card_does_not_recommend_investigating_nonexistent_forecasts():
    answer = _fallback_answer_from_metadata(
        {
            "metrics": _metrics(),
            "tables": [
                _alerts(),
                {"kind": "forecasts", "items": []},
            ],
        }
    )

    assert "Получено 0 прогнозов" not in answer
    assert "проверь прогнозы" not in answer


@pytest.mark.django_db
def test_visible_answer_replaces_legacy_placeholder_and_returns_streamable_text():
    user = User.objects.create_user(username="operator-summary", password="x")
    session = ChatSession.objects.create(user=user, title="Summary")
    message = ChatMessage.objects.create(
        session=session,
        role=ChatMessage.ROLE_ASSISTANT,
        content="Метрики — карточка ниже.",
        metadata={"metrics": _metrics()},
    )

    streamed = async_to_sync(_ensure_visible_answer)(message.pk)
    message.refresh_from_db()

    assert streamed == message.content
    assert "CPU 31%" in streamed
    assert not _is_card_placeholder(message.content)


def test_operator_prompt_requires_text_report_before_supporting_cards():
    assert "The text is the report" in OPERATOR_SYSTEM_PROMPT
    assert "never a replacement for the answer" in OPERATOR_SYSTEM_PROMPT
    assert "Never answer only" in OPERATOR_SYSTEM_PROMPT
