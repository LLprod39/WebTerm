from __future__ import annotations

from loguru import logger

from app.agent_kernel.mcp_runtime import describe_mcp_bindings
from app.core.llm import LLMProvider
from app.execution_policy import safe_payload_preview
from app.sudo_policy import sudo_policy_prompt
from servers.agent_inputs import build_agent_materials_prompt
from servers.agent_tools import get_tools_description


def build_system_prompt(engine) -> str:
    connected = engine.session.get_connected_info()
    servers_desc = "\n".join(f"- {c['server_name']} (id: {c['server_id']})" for c in connected) or "- Нет активных SSH подключений"
    all_servers_desc = (
        "\n".join(f"- {s.name} (id: {s.id}, host: {s.host})" for s in engine.servers) or "- SSH серверы не выбраны"
    )

    custom_system = engine.agent.system_prompt or ""
    materials_prompt = build_agent_materials_prompt(engine.agent.input_artifacts)
    tools_desc = get_tools_description(engine.enabled_tools)
    mcp_tools_desc = describe_mcp_bindings(engine._mcp_runtime_provider, engine.mcp_tools)
    skills_desc = engine._skill_provider.build_skill_catalog_description(engine.skills) if engine._skill_provider else ""
    if mcp_tools_desc:
        tools_desc = f"{tools_desc}\n\n{mcp_tools_desc}" if tools_desc else mcp_tools_desc

    stop_conditions = ""
    if engine.agent.stop_conditions:
        stop_conditions = "\nStop conditions:\n" + "\n".join(f"- {c}" for c in engine.agent.stop_conditions)

    mcp_errors = ""
    if engine.mcp_tool_errors:
        mcp_errors = "\n## MCP подключения с ошибками\n" + "\n".join(f"- {item}" for item in engine.mcp_tool_errors)

    skill_errors = ""
    if engine.skill_errors:
        skill_errors = "\n## Skills с ошибками\n" + "\n".join(f"- {item}" for item in engine.skill_errors)

    tool_rules = [
        "- ВСЕГДА сначала выводи THOUGHT с объяснением логики рассуждений",
        "- Затем выводи ACTION с вызовом инструмента в формате JSON",
        "- После каждой команды анализируй вывод и решай, что делать дальше",
        "- Для внешних систем (Keycloak, GitHub, Docker API, cloud, IAM) используй MCP-инструменты, если они доступны",
        "- Имена MCP-инструментов нужно использовать ТОЧНО как перечислено в секции инструментов",
        "- Если подключены skills, сначала ориентируйся по их каталогу и открывай полный skill через read_skill перед сервис-специфичными изменениями",
        "- Некоторые skills дополнительно применяют runtime guardrails к MCP-вызовам: могут подставлять обязательные аргументы и блокировать опасные действия",
        "- НЕ запускай опасные команды (rm -rf, mkfs, shutdown и т.д.) — они будут заблокированы",
        f"- {sudo_policy_prompt(engine.permission_engine.sudo_policy)}",
        "- Когда цель полностью достигнута, предоставь итоговый анализ БЕЗ строки ACTION",
        f"- Максимум {engine.max_iterations} итераций доступно",
    ]
    if "send_ctrl_c" in engine.enabled_tools:
        tool_rules.append("- Если команда выполняется слишком долго (>30с), используй send_ctrl_c для прерывания")
    if "read_console" in engine.enabled_tools:
        tool_rules.append("- Используй read_console для проверки текущего состояния терминала, если не уверен")
    if "ask_user" in engine.enabled_tools:
        tool_rules.append("- Используй ask_user только когда действительно нужен ввод человека для критического решения")
    if "report" in engine.enabled_tools:
        tool_rules.append("- Используй report для отправки промежуточного отчёта пользователю при длительных задачах")
    rules_text = "\n".join(tool_rules)

    return f"""Ты — DevOps / Platform AI-агент, работающий через SSH и MCP-инструменты.
У тебя есть доступ к терминалам серверов и внешним системам, подключённым через MCP.
Всегда отвечай, рассуждай и пиши отчёты на русском языке.

{engine.ops_prompt_context}

{custom_system}

{materials_prompt}

## Подключённые серверы
{servers_desc}

## Все доступные серверы (можно подключиться через open_connection)
{all_servers_desc}

## Attached skills
{skills_desc or "- Skills не подключены"}

## Доступные инструменты
{tools_desc}

## Правила
{rules_text}
{stop_conditions}
{mcp_errors}
{skill_errors}

## Формат вывода
THOUGHT: <твоё рассуждение о том, что делать дальше>
ACTION: tool_name {{"param1": "value1", "param2": "value2"}}

Когда задача завершена (больше нет действий), выведи итоговый анализ БЕЗ строки ACTION."""


async def generate_final_report(engine, history: list[dict], iterations: list[dict]) -> str:
    summary_parts = []
    for item in iterations:
        if item.get("action"):
            summary_parts.append(
                f"Step {item['iteration']}: {item['action']}({safe_payload_preview(item.get('args', {}), limit=100)}) → "
                f"{item['observation'][:200]}"
            )
        else:
            summary_parts.append(f"Step {item['iteration']}: Final answer")

    steps_summary = "\n".join(summary_parts[-20:])
    prompt = f"""Ты — технический аналитик. Создай профессиональный структурированный отчёт в формате Markdown.
Язык: русский. Стиль: деловой, конкретный, без воды.

Данные для отчёта:
- Агент: {engine.agent.name}
- Цель: {engine.agent.goal or engine.agent.ai_prompt or 'Не указана'}
- Итераций выполнено: {len(iterations)}
- Шаги агента: {steps_summary}
- Итоговый ответ агента: {history[-1]['content'][:3000] if history else 'Нет данных'}

Сгенерируй отчёт СТРОГО в следующем формате — не добавляй лишних секций, не меняй структуру:

# [Краткое название того что было сделано]

> [Одно предложение — главный итог работы агента]

## Результат

[2–4 предложения об общем результате и текущем состоянии системы]

## Выполненные действия

- [Действие 1 — конкретно что сделано и что получено]
- [Действие 2]
- [...]

## Ключевые находки

- [Находка 1 — факт с конкретными данными: цифры, названия, пути]
- [Находка 2]
- [...]

## Рекомендации

- [Рекомендация 1 — конкретное действие]
- [Рекомендация 2]

---

**Статус:** ✅ Успех / ⚠️ Частичный успех / ❌ Ошибка"""

    provider = LLMProvider()
    chunks = []
    try:
        logger.info(
            "agent_run {} final report llm start: iterations={}",
            engine.run_record.pk if engine.run_record else "?",
            len(iterations),
        )
        async for chunk in provider.stream_chat(
            prompt,
            model=engine.model_preference,
            specific_model=engine.specific_model,
            purpose="opssummary",
        ):
            chunks.append(chunk)
        report = "".join(chunks)
        logger.info(
            "agent_run {} final report llm done: chars={}",
            engine.run_record.pk if engine.run_record else "?",
            len(report),
        )
        return report
    except Exception as exc:
        logger.error("Final report generation failed: {}", exc)
        return f"Report generation failed: {exc}\n\nRaw steps:\n{steps_summary}"
