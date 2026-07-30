from types import SimpleNamespace

from servers.agents.agent_engine_prompts import build_fallback_final_report
from servers.agents.multi_agent_plan_helpers import build_tasks_table
from servers.agents.multi_agent_planning import _fallback_multi_agent_report


def test_full_agent_fallback_report_keeps_required_sections():
    engine = SimpleNamespace(
        agent=SimpleNamespace(
            name="Fallback Agent",
            goal="Проверить сервис",
            ai_prompt="",
        )
    )
    report = build_fallback_final_report(
        engine,
        [
            {
                "iteration": 1,
                "action": "ssh_execute",
                "args": {"command": "systemctl status nginx"},
                "observation": "nginx active",
            }
        ],
        error="llm unavailable",
    )

    assert "# Отчёт агента: Fallback Agent" in report
    for section in (
        "## Что произошло",
        "## Итог",
        "## Доказательства",
        "## Выполненные действия",
        "## Ключевые находки",
        "## Проблемы и риски",
        "## Рекомендации",
        "**Статус:**",
    ):
        assert section in report
    assert "llm unavailable" in report
    assert "nginx active" in report


def test_multi_agent_fallback_report_keeps_required_sections_and_task_table():
    tasks = [
        {
            "id": 1,
            "name": "Проверить nginx",
            "description": "systemctl status nginx",
            "status": "done",
            "result": "nginx active",
        },
        {
            "id": 2,
            "name": "Проверить disk",
            "description": "df -h",
            "status": "failed",
            "error": "disk command failed",
        },
    ]
    report = _fallback_multi_agent_report(
        "Проверить прод",
        tasks,
        build_tasks_table(tasks),
        error="empty report",
    )

    for section in (
        "## Что произошло",
        "## Итог",
        "## Результаты по задачам",
        "## Доказательства",
        "## Ключевые находки",
        "## Проблемы и риски",
        "## Рекомендации",
        "**Статус пайплайна:**",
    ):
        assert section in report
    assert "Проверить nginx" in report
    assert "disk command failed" in report
