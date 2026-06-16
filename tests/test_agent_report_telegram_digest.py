from types import SimpleNamespace

from servers.agent_inputs import format_telegram_report_message


def test_telegram_agent_report_is_brief_digest():
    report = """
# Docker status report

## Резюме
Все контейнеры запущены и в состоянии healthy. Основная проблема - занятое место образами и build cache.

## Обнаружения
- Images 15.58 GB, reclaimable 8.12 GB.
- Build Cache 11.04 GB, активных записей 0.
- Контейнеры работают стабильно, циклов рестарта нет.

## Рекомендации
Быть осторожными с удалением: сначала проверить, какие образы и volumes реально не используются.
docker system df -v
docker builder prune --all --force
"""
    run = SimpleNamespace(
        id=321,
        status="completed",
        final_report=report,
        ai_analysis="",
        agent=SimpleNamespace(name="Статус Docker"),
    )

    message = format_telegram_report_message(run, site_url="http://127.0.0.1:8080", include_link=True)

    assert len(message) < 950
    assert "<b>Отчет: Статус Docker</b>" in message
    assert "<b>Статус:</b> OK (completed)" in message
    assert "Главное:" in message
    assert "Images 15.58 GB" in message
    assert "Дальше:" in message
    assert "docker system df -v" not in message
    assert "**" not in message
    assert "... отчет сокращен" not in message
    assert '<a href="http://127.0.0.1:8080/agents/run/321">Открыть полный отчет</a>' in message
