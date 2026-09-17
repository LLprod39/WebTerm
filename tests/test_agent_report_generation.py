from types import SimpleNamespace

import pytest

from servers.agents.agent_engine_prompts import build_fallback_final_report
from servers.agents.agent_report_compact import (
    COMPACT_REPORT_MAX_CHARS,
    build_control_plane_report,
    coerce_compact_report,
    collapse_repeated_compact_blocks,
)
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

    assert "# Отчёт агента" in report or engine.agent.name in report
    assert "## Что произошло" not in report
    assert "## Рекомендации" not in report
    assert "**Статус:**" in report
    assert "nginx active" in report
    assert "llm unavailable" in report
    assert "канал выполнения недоступен" not in report
    assert len(report) <= COMPACT_REPORT_MAX_CHARS


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

    assert "## Что произошло" not in report
    assert "## Результаты по задачам" in report
    assert "**Статус пайплайна:**" in report
    assert "## Доказательства" not in report
    assert "Проверить nginx" in report
    assert "disk command failed" in report


def test_control_plane_report_skips_ssh_narrative():
    engine = SimpleNamespace(
        agent=SimpleNamespace(name="Проверка логов", goal="Снять логи", ai_prompt=""),
        servers=[SimpleNamespace(name="nikitavm")],
        _control_plane_blocked=True,
    )
    iterations = [
        {
            "iteration": 1,
            "action": "ssh_execute",
            "args": {"command": "docker ps -a"},
            "observation": (
                "CONTROL_PLANE: канал выполнения на хосте WebTerm недоступен "
                "(Docker API). permission denied unix:///var/run/docker.sock"
            ),
        }
    ]
    report = build_fallback_final_report(engine, iterations)
    assert report == build_control_plane_report(engine, iterations)
    assert "не запускались" in report
    assert "SSH до цели не проверялся" in report
    assert "DOCKER_SOCKET_GID" in report
    assert "Контекст запуска" not in report
    assert len(report) <= COMPACT_REPORT_MAX_CHARS


def test_coerce_compact_report_rejects_meta_sections():
    fallback = "# Короткий\n\n> Итог.\n\n- Факт\n\n**Статус:** ❌ Ошибка"
    verbose = "# Заголовок\n\n> Цитата\n\n## Контекст запуска\n\nМного воды\n- Факт из журнала\n\n**Статус:** ❌ Ошибка\n"
    result = coerce_compact_report(verbose, fallback=fallback)
    assert result != fallback
    assert "## Контекст запуска" not in result
    assert "# Заголовок" in result
    assert "> Цитата" in result
    assert "- Факт из журнала" in result
    assert coerce_compact_report(fallback, fallback="x") == fallback
    only_meta = "## Контекст запуска\n\nМного воды без каркаса\n"
    assert coerce_compact_report(only_meta, fallback=fallback) == fallback


def test_coerce_compact_report_collapses_repeated_glued_skeleton():
    duplicated = """# Логи на nikitavm не проверены — нет SSH/MCP
> Live-чтение логов контейнеров недоступно: в сессии нет SSH/MCP из Ops-профиля.
- Цель: только чтение логов контейнеров на `nikitavm`, без изменений- Итераций: 1- Проверен каталог dynamic tools- Итог агента: выполнить проверку нельзя из‑за отсутствия нужных инструментов
Дальше: подключить Ops SSH/MCP и повторить запрос.
**Статус:** ❌ Ошибка# Логи на nikitavm не проверены — нет SSH/MCP

> Live-чтение логов контейнеров недоступно: в сессии нет SSH/MCP из Ops-профиля.

- Цель: только чтение логов контейнеров на `nikitavm`, без изменений
- Итераций: 1
- Проверен каталог dynamic tools
- Итог агента: выполнить проверку нельзя из‑за отсутствия нужных инструментов

Дальше: подключить Ops SSH/MCP и повторить запрос.

**Статус:** ❌ Ошибка# Логи на nikitavm не проверены — нет SSH/MCP

> Live-чтение логов контейнеров недоступно: в сессии нет SSH/MCP из Ops-профиля.

- Цель: только чтение логов контейнеров на `nikitavm`, без изменений
- Итераций: 1
- Проверен каталог dynamic tools
- Итог агента: выполнить проверку нельзя из‑за отсутствия нужных инструментов

Дальше: подключить Ops SSH/MCP и повторить запрос.

**Статус:** ❌ Ошибка
"""
    fallback = "# fallback\n"
    result = coerce_compact_report(duplicated, fallback=fallback)
    assert result != fallback
    assert result.count("# Логи на nikitavm не проверены") == 1
    assert result.count("**Статус:**") == 1
    assert result.count("Live-чтение логов") == 1
    assert "- Итераций: 1" in result
    assert "- Проверен каталог dynamic tools" in result
    assert "без изменений- Итераций" not in result
    assert "Ошибка#" not in result


def test_collapse_keeps_verification_and_outcome_tail():
    duplicated = """# Логи на nikitavm не проверены — нет SSH/MCP
> Нет канала.
- Итераций: 1
**Статус:** ❌ Ошибка# Логи на nikitavm не проверены — нет SSH/MCP
> Нет канала.
- Итераций: 1
**Статус:** ❌ Ошибка

## Контроль изменений
- Все обязательные post-change verification markers закрыты.

---
Outcome: partial — Final answer without tool evidence while tools were available
"""
    result = collapse_repeated_compact_blocks(duplicated)
    assert result.count("# Логи на nikitavm не проверены") == 1
    assert "## Контроль изменений" in result
    assert "---" in result
    assert "Outcome: partial" in result
    assert "Ошибка#" not in result


def test_coerce_compact_report_keeps_distinct_h1_sections():
    markdown = """# Первый итог

> Команда прошла.

- nginx active

**Статус:** ✅ Успех

# Второй итог

> Диск не проверен.

- df failed

**Статус:** ❌ Ошибка
"""
    result = coerce_compact_report(markdown, fallback="# fallback")
    assert result.count("# Первый итог") == 1
    assert result.count("# Второй итог") == 1
    assert "nginx active" in result
    assert "df failed" in result


def test_coerce_compact_report_truncates_over_limit_instead_of_fallback():
    facts = "\n".join(f"- Факт {index}: " + ("контейнер " * 40) for index in range(5))
    verbose = (
        "# Логи сняты частично\n\n"
        "> Агент обошёл часть контейнеров и остановился на LLM.\n\n"
        f"{facts}\n\n"
        "Дальше: Проверить оставшиеся контейнеры.\n\n"
        "**Статус:** ⚠️ Частичный успех"
    )
    fallback = "# fallback\n\nsudo -n docker logs nginx\n"
    assert len(verbose) > COMPACT_REPORT_MAX_CHARS
    result = coerce_compact_report(verbose, fallback=fallback)
    assert result != fallback
    assert "sudo -n docker logs" not in result
    assert "# Логи сняты частично" in result
    assert "**Статус:**" in result
    assert len(result) <= COMPACT_REPORT_MAX_CHARS


def test_coerce_extracts_skeleton_from_verbose_banned_report():
    verbose = """# Логи контейнеров на nikitavm

> Проверены running-контейнеры; в pipeline-execution старый DB traceback.

## Что произошло
Много воды про контекст запуска и оценку цели.

- docker logs mini-prod-pipeline-execution: OperationalError 2026-08-14
- Остальные просмотренные контейнеры без свежих error/fatal

Дальше: разобрать AdminShutdown БД, если ошибка повторится.

**Статус:** ⚠️ Частичный успех
"""
    verbose = verbose + ("абзац " * 400)
    fallback = "# Проверка логов: итог по журналу\n\n> Полный LLM-отчёт недоступен\n\n- ssh_execute: Sudo разрешён"
    assert len(verbose) > COMPACT_REPORT_MAX_CHARS
    result = coerce_compact_report(verbose, fallback=fallback)
    assert "итог по журналу" not in result
    assert "Sudo разрешён" not in result
    assert "## Что произошло" not in result
    assert "OperationalError" in result
    assert "**Статус:**" in result
    assert len(result) <= COMPACT_REPORT_MAX_CHARS


def test_fallback_report_uses_commands_not_raw_log_tail():
    engine = SimpleNamespace(
        agent=SimpleNamespace(name="Проверка логов", goal="Снять логи", ai_prompt=""),
    )
    report = build_fallback_final_report(
        engine,
        [
            {
                "iteration": 1,
                "action": "ssh_execute",
                "args": {"command": "docker logs nginx --tail 100"},
                "observation": "sudo -n docker logs nginx " + ("Sep 16 error line " * 30),
            }
        ],
        exit_reason="llm_error",
        tool_calls=[{"tool": "ssh_execute", "success": True}],
    )
    assert "docker logs nginx --tail 100" in report
    assert "sudo -n docker logs" not in report
    assert "оборвался на LLM" in report
    assert "Частичный успех" in report
    assert len(report) <= COMPACT_REPORT_MAX_CHARS


def test_fallback_uses_command_and_strips_sudo_preamble():
    engine = SimpleNamespace(
        agent=SimpleNamespace(name="Проверка логов", goal="Проверить логи контейнеров", ai_prompt=""),
    )
    report = build_fallback_final_report(
        engine,
        [
            {
                "iteration": 20,
                "action": "ssh_execute",
                "args": {"command": "sudo docker logs --tail 100 webtrerm-prod-operator-execution-1", "server": "nikitavm"},
                "observation": (
                    "Sudo разрешён для этого запуска; команда будет выполнена в non-interactive режиме sudo -n.\n\n"
                    "STDERR: Traceback (most recent call last):\n"
                    "django.db.utils.OperationalError: terminating connection due to administrator command\n"
                ),
            }
        ],
        exit_reason="llm_error",
        tool_calls=[{"tool": "ssh_execute", "success": True}],
    )
    assert "sudo docker logs --tail 100 webtrerm-prod-operator-execution-1" in report
    assert "Sudo разрешён" not in report
    assert "ssh_execute:" not in report
    assert "оборвался на LLM" in report
    assert "Полный LLM-отчёт недоступен" not in report


@pytest.mark.asyncio
async def test_generate_final_report_keeps_overlong_compact_llm(monkeypatch):
    from servers.agents.agent_engine_prompts import generate_final_report

    facts = "\n".join(f"- Факт {index}: " + ("контейнер " * 40) for index in range(5))
    long_report = (
        "# Логи сняты частично\n\n"
        "> Агент обошёл часть контейнеров и остановился.\n\n"
        f"{facts}\n\n"
        "Дальше: Проверить оставшиеся контейнеры.\n\n"
        "**Статус:** ⚠️ Частичный успех"
    )
    assert len(long_report) > COMPACT_REPORT_MAX_CHARS

    class FakeProvider:
        async def stream_chat(self, *_args, **_kwargs):
            yield long_report

    async def fake_context(_purpose):
        return None

    monkeypatch.setattr("servers.agents.agent_engine_prompts.LLMProvider", FakeProvider)
    engine = SimpleNamespace(
        agent=SimpleNamespace(name="Проверка логов", goal="Снять логи", ai_prompt=""),
        servers=[],
        _control_plane_blocked=False,
        model_preference="auto",
        specific_model="",
        run_record=SimpleNamespace(pk=2166),
        _execution_context_for=fake_context,
    )
    report = await generate_final_report(
        engine,
        [{"role": "assistant", "content": "продолжаю"}],
        [
            {
                "iteration": 1,
                "action": "ssh_execute",
                "args": {"command": "docker logs nginx --tail 100"},
                "observation": "ok",
            }
        ],
        exit_reason="llm_error",
        tool_calls=[{"tool": "ssh_execute", "success": True}],
    )
    assert "# Логи сняты частично" in report
    assert "итог по журналу" not in report
    assert len(report) <= COMPACT_REPORT_MAX_CHARS


@pytest.mark.asyncio
async def test_generate_final_report_skips_llm_on_control_plane(monkeypatch):
    from servers.agents.agent_engine_prompts import generate_final_report

    def boom(*_args, **_kwargs):
        raise AssertionError("LLM must not run for control-plane failures")

    monkeypatch.setattr("servers.agents.agent_engine_prompts.LLMProvider", boom)
    engine = SimpleNamespace(
        agent=SimpleNamespace(name="Проверка логов", goal="Снять логи", ai_prompt=""),
        servers=[SimpleNamespace(name="nikitavm")],
        _control_plane_blocked=True,
        model_preference="auto",
        specific_model="",
        run_record=SimpleNamespace(pk=2165),
    )
    report = await generate_final_report(
        engine,
        [{"role": "assistant", "content": "длинный монолог " * 200}],
        [
            {
                "iteration": 1,
                "action": "ssh_execute",
                "observation": "CONTROL_PLANE: permission denied unix:///var/run/docker.sock",
            }
        ],
    )
    assert "нет доступа к Docker" in report
    assert "длинный монолог" not in report
    assert len(report) <= COMPACT_REPORT_MAX_CHARS


