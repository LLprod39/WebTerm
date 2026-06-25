from __future__ import annotations

from typing import Any

from django.utils import timezone
from loguru import logger

from app.agent_kernel.domain.roles import ROLE_SPECS
from app.core.llm import LLMProvider
from servers.agent_inputs import build_agent_materials_prompt
from servers.multi_agent_engine_config import MAX_PLAN_TASKS
from servers.multi_agent_plan_helpers import (
    build_tasks_table,
    inject_tasks_table_into_report,
    parse_decision_response,
    parse_plan_response,
)


async def plan_multi_agent_tasks(engine: Any, goal: str, orchestrator_log: list) -> list[dict]:
    """Call the orchestrator LLM and turn its response into executable tasks."""
    connected = engine.session.get_connected_info()
    servers_desc = "\n".join(f"- {c['server_name']} (id: {c['server_id']})" for c in connected)
    custom_system = engine.agent.system_prompt or ""
    materials_prompt = build_agent_materials_prompt(engine.agent.input_artifacts)
    skills_desc = engine._skill_provider.build_skill_catalog_description(engine.skills) if engine._skill_provider else ""
    role_options = "\n".join(
        f"- {slug}: {spec.title}; фокус: {', '.join(spec.focus_areas)}"
        for slug, spec in ROLE_SPECS.items()
        if slug != "custom"
    )
    skill_errors = ""
    if engine.skill_errors:
        skill_errors = "\nSkills с ошибками:\n" + "\n".join(f"- {item}" for item in engine.skill_errors)

    system_prompt = f"""Ты — мастер-оркестратор DevOps-агентов. Твоя задача — разбить цель на конкретные задачи для исполнительных агентов.
Каждый агент умеет: выполнять SSH-команды, читать файлы, проверять сервисы, анализировать логи.
Отвечай ТОЛЬКО валидным JSON-массивом. Без пояснений до или после JSON.
{engine.ops_prompt_context}
{custom_system}
{materials_prompt}

Подключённые серверы:
{servers_desc}

Attached skills:
{skills_desc or "- Skills не подключены"}
{skill_errors}

Правила декомпозиции:
- Максимум {MAX_PLAN_TASKS} задач
- Каждая задача должна быть самодостаточной и конкретной
- Используй русский язык для имён и описаний
- Порядок задач важен — они выполняются последовательно
- Каждая задача должна быть выполнима за 5-7 SSH-команд максимум
- Если attached skills содержат runtime guardrails, учитывай их как обязательные ограничения

Доступные subagent roles:
{role_options}"""

    user_msg = f"""Цель: {goal}

Верни JSON-массив задач в формате:
[
  {{
    "name": "Краткое название задачи",
    "description": "Что именно нужно сделать, какие команды запустить, что проверить",
    "role": "incident_commander|deploy_operator|infra_scout|log_investigator|security_patrol|post_change_verifier|watcher_daemon|custom"
  }},
  ...
]"""

    orchestrator_log.append({"role": "system", "content": system_prompt, "timestamp": timezone.now().isoformat()})
    orchestrator_log.append({"role": "user", "content": user_msg, "timestamp": timezone.now().isoformat()})

    response = await engine._call_llm_raw(system_prompt, user_msg)
    orchestrator_log.append({"role": "assistant", "content": response, "timestamp": timezone.now().isoformat()})

    tasks = parse_plan_response(
        response,
        max_tasks=MAX_PLAN_TASKS,
        fallback_goal=engine.agent.goal or engine.agent.ai_prompt,
    )
    return engine._prepare_plan_tasks(tasks)


async def handle_multi_agent_failure(
    engine: Any,
    failed_task: dict,
    error: str,
    all_tasks: list[dict],
    orchestrator_log: list,
) -> dict:
    """Ask the orchestrator LLM what to do after a task failure."""
    done_tasks = [t for t in all_tasks if t["status"] == "done"]
    pending_tasks = [t for t in all_tasks if t["status"] == "pending"]

    system_prompt = """Ты — оркестратор агентного пайплайна. Одна из задач завершилась с ошибкой.
Реши, что делать дальше. Ответь ТОЛЬКО валидным JSON-объектом без пояснений."""

    timeout_hint = ""
    if "Session timeout" in error or "session timeout" in error.lower():
        timeout_hint = (
            "\n\nВажно: при ошибке «Session timeout» лимит времени сессии исчерпан. "
            "Лучше выбрать \"replan\" — перепланировать оставшуюся работу (меньше/проще задач), чтобы уложиться во время и довести цель до конца."
        )

    user_msg = f"""Задача, которая упала: {failed_task['name']}
Описание: {failed_task['description']}
Ошибка: {error}

Уже выполнено задач: {len(done_tasks)}
Осталось задач: {len(pending_tasks)}
{timeout_hint}

Доступные действия:
- "replan"   — перепланировать: составить НОВЫЙ план оставшихся задач с учётом сделанного и ошибок (меньше задач, проще формулировки), чтобы достичь цели
- "retry"    — повторить эту задачу ещё раз
- "skip"     — пропустить и продолжить со следующей задачей
- "ask_user" — спросить пользователя (нужно поле "message" с вопросом)
- "abort"    — прервать весь пайплайн (нужно поле "reason")

Верни JSON:
{{"action": "replan"|"retry"|"skip"|"ask_user"|"abort", "reason": "...", "message": "..."}}"""

    orchestrator_log.append({"role": "user", "content": user_msg, "timestamp": timezone.now().isoformat()})
    response = await engine._call_llm_raw(system_prompt, user_msg)
    orchestrator_log.append({"role": "assistant", "content": response, "timestamp": timezone.now().isoformat()})

    return parse_decision_response(response)


async def replan_multi_agent_tasks(engine: Any, goal: str, plan_tasks: list[dict], orchestrator_log: list) -> list[dict]:
    """Produce a short replacement plan for remaining work."""
    done_tasks = [t for t in plan_tasks if t["status"] == "done"]
    failed_or_skipped = [t for t in plan_tasks if t["status"] in ("failed", "skipped")]
    pending_tasks = [t for t in plan_tasks if t["status"] == "pending"]

    done_block = "\n".join(
        f"- {t['name']}: { (t.get('result') or '')[:300]}"
        for t in done_tasks
    ) or "(нет)"
    failed_block = "\n".join(
        f"- {t['name']}: ошибка — {t.get('error', '')[:200]}"
        for t in failed_or_skipped
    ) or "(нет)"
    pending_block = "\n".join(
        f"- {t['name']}: {t.get('description', '')[:200]}"
        for t in pending_tasks
    ) or "(нет)"

    system_prompt = """Ты — оркестратор. Нужно перепланировать оставшуюся работу с учётом полной картины.
Учитывай уже выполненное, провалы и ограничения (например нехватка времени). Составь НОВЫЙ короткий план задач, чтобы достичь исходной цели.
Отвечай ТОЛЬКО валидным JSON-массивом задач. Без пояснений до или после JSON."""

    user_msg = f"""Цель пайплайна: {goal}

Уже выполнено (результаты):
{done_block}

Провалено или пропущено (ошибки):
{failed_block}

Не начато по старому плану:
{pending_block}

Составь НОВЫЙ план — только те задачи, которые ОСТАЛОСЬ выполнить для достижения цели. Учитывай сделанное (не дублируй). Для проваленного — упрости или объедини задачи. Сократи число задач (макс. {MAX_PLAN_TASKS}), чтобы уложиться во время. Каждая задача — конкретные команды/шаги.

Формат ответа — JSON-массив:
[
  {{"name": "Краткое название", "description": "Что сделать"}},
  ...
]"""

    orchestrator_log.append({"role": "user", "content": user_msg, "timestamp": timezone.now().isoformat()})
    response = await engine._call_llm_raw(system_prompt, user_msg)
    orchestrator_log.append({"role": "assistant", "content": response, "timestamp": timezone.now().isoformat()})

    tasks = parse_plan_response(
        response,
        max_tasks=MAX_PLAN_TASKS,
        fallback_goal=engine.agent.goal or engine.agent.ai_prompt,
    )
    return engine._prepare_plan_tasks(tasks[:MAX_PLAN_TASKS])


async def synthesize_multi_agent_report(engine: Any, goal: str, plan_tasks: list[dict], orchestrator_log: list) -> str:
    """Generate the final consolidated report."""
    task_summaries = []
    for task in plan_tasks:
        status_emoji = {"done": "✅", "failed": "❌", "skipped": "⏭️", "running": "⚠️"}.get(task["status"], "❓")
        result_text = task.get("result", "") or task.get("error", "Нет данных")
        task_summaries.append(f"{status_emoji} **{task['name']}**: {result_text[:400]}")

    tasks_block = "\n\n".join(task_summaries)
    tasks_table = build_tasks_table(plan_tasks)

    system_prompt = """Ты — старший технический аналитик. Создай профессиональный деловой отчёт в формате Markdown.
Язык: русский. Стиль: чёткий, структурированный, без воды. Только факты и конкретные данные.

ПРАВИЛА ФОРМАТИРОВАНИЯ:
- В отчёте секция «Результаты по задачам» уже заполнена готовой таблицей — НЕ переписывай и НЕ меняй её.
- Списки — через дефис (-), без лишних отступов.
- Не повторяй одно и то же в разных секциях.
- Если корневая причина не подтверждена фактами, так и напиши; не выдумывай её."""

    user_msg = f"""Создай финальный отчёт по результатам работы агентного пайплайна.

Цель пайплайна: {goal}

Результаты задач (для контекста):
{tasks_block}

Сгенерируй отчёт СТРОГО в следующем формате. Секцию «Результаты по задачам» оформи ТОЧНО так (скопируй таблицу как есть):

# [Название — кратко суть результата]

> [Одно предложение — главный итог пайплайна]

## Что произошло

[2–4 предложения: какая цель была у пайплайна, какие агенты/серверы участвовали, чем завершился запуск]

## Итог

[3–4 предложения: общий результат, статус системы, ключевые выводы]

## Результаты по задачам

{tasks_table}

## Доказательства

- [Факт 1 — конкретный результат задачи, команда, статус сервиса, число, путь или версия]
- [Факт 2]

## Ключевые находки

- **[Категория]:** [Факт с конкретными данными — цифры, имена, версии]
- **[Категория]:** [...]

## Проблемы и риски

- [Проблема — что обнаружено и почему важно]
- [Если критических проблем нет — написать: Критических проблем не обнаружено]

## Рекомендации

1. [Конкретное действие — что именно сделать]
2. [Следующий шаг]

---

**Статус пайплайна:** ✅ Успех / ⚠️ Частичный успех / ❌ Ошибка"""

    orchestrator_log.append({"role": "user", "content": user_msg, "timestamp": timezone.now().isoformat()})
    provider = LLMProvider()
    chunks = []
    try:
        with engine._audit_scope():
            async for chunk in provider.stream_chat(
                f"[SYSTEM]\n{system_prompt}\n\n[USER]\n{user_msg}",
                model=engine.model_preference,
                specific_model=engine.specific_model,
                purpose="opssummary",
            ):
                chunks.append(chunk)
                if chunks and len(chunks) % 20 == 0:
                    await engine._emit("agent_report", {"text": "".join(chunks), "interim": True})
        result = "".join(chunks).strip()
        if not result:
            return _fallback_multi_agent_report(goal, plan_tasks, tasks_table, error="LLM вернул пустой финальный отчёт")
        orchestrator_log.append({"role": "assistant", "content": result, "timestamp": timezone.now().isoformat()})
        return inject_tasks_table_into_report(result, tasks_table)
    except Exception as exc:
        logger.error("Synthesis failed: {}", exc)
        return _fallback_multi_agent_report(goal, plan_tasks, tasks_table, error=str(exc))


def _fallback_multi_agent_report(goal: str, plan_tasks: list[dict], tasks_table: str, *, error: str = "") -> str:
    done = [task for task in plan_tasks if task.get("status") == "done"]
    failed = [task for task in plan_tasks if task.get("status") == "failed"]
    skipped = [task for task in plan_tasks if task.get("status") == "skipped"]
    evidence = []
    for task in plan_tasks[:8]:
        result_text = str(task.get("result") or task.get("error") or task.get("thought") or "").strip()
        if result_text:
            evidence.append(f"- {task.get('name', 'Задача')}: {result_text[:240]}")
    if not evidence:
        evidence = ["- Сохранённых результатов задач недостаточно для технического вывода."]

    risk_lines = []
    if failed:
        risk_lines.extend(f"- Задача не выполнена: {task.get('name', 'Без названия')}" for task in failed[:5])
    if skipped:
        risk_lines.extend(f"- Задача пропущена: {task.get('name', 'Без названия')}" for task in skipped[:5])
    if error:
        risk_lines.append(f"- Генерация LLM-отчёта завершилась ошибкой: {error[:500]}")
    if not risk_lines:
        risk_lines = ["- Критических проблем не обнаружено по сохранённым задачам; полнота вывода требует ручной проверки."]

    status = "❌ Ошибка" if failed else "⚠️ Частичный успех"
    return f"""# Отчёт пайплайна

> Финальный Markdown собран детерминированным fallback по сохранённым задачам пайплайна.

## Что произошло

Пайплайн выполнял цель: {goal}. Основной LLM-синтез финального отчёта не дал полноценный структурированный результат, поэтому backend сформировал безопасный fallback-отчёт из сохранённых задач.

## Итог

Выполнено задач: {len(done)} из {len(plan_tasks)}. Корневая причина не подтверждена фактами; вывод ниже основан только на сохранённых результатах задач.

## Результаты по задачам

{tasks_table}

## Доказательства

{chr(10).join(evidence)}

## Ключевые находки

- Доступно задач пайплайна: {len(plan_tasks)}.
- Успешно завершено задач: {len(done)}.
- Провалено задач: {len(failed)}.

## Проблемы и риски

{chr(10).join(risk_lines)}

## Рекомендации

1. Проверить вкладки «События», «Логи» и «Ход агента» для первичных данных.
2. Повторить запуск или перепланировать оставшиеся задачи после устранения проблем.

---

**Статус пайплайна:** {status}"""
