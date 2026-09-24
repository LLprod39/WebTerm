from __future__ import annotations

from loguru import logger

from app.agent_kernel.mcp_runtime import describe_mcp_bindings
from app.agent_kernel.runtime.outcomes import (
    EXIT_CONTROL_PLANE,
    EXIT_LLM_ERROR,
    EXIT_TIMEOUT,
    summarize_tool_evidence,
)
from app.agent_kernel.sandbox.runtime_errors import is_control_plane_text
from app.core.llm import LLMProvider, is_thinking_chunk
from app.sudo_policy import sudo_policy_prompt
from servers.agents.agent_inputs import build_agent_materials_prompt
from servers.agents.agent_report_compact import (
    COMPACT_REPORT_MAX_CHARS,
    build_compact_report,
    build_control_plane_report,
    coerce_compact_report,
    compact_journal_facts,
    compact_steps_summary,
    iterations_have_control_plane,
)
from servers.agents.agent_tools import get_tools_description


def build_system_prompt(engine) -> str:
    connected = engine.session.get_connected_info()
    servers_desc = (
        "\n".join(f"- {c['server_name']} (id: {c['server_id']})" for c in connected) or "- Нет активных SSH подключений"
    )
    all_servers_desc = (
        "\n".join(f"- {s.name} (id: {s.id}, host: {s.host})" for s in engine.servers) or "- SSH серверы не выбраны"
    )

    custom_system = engine.agent.system_prompt or ""
    materials_prompt = build_agent_materials_prompt(engine.agent.input_artifacts)
    tools_desc = get_tools_description(engine.enabled_tools)
    mcp_tools_desc = describe_mcp_bindings(engine._mcp_runtime_provider, engine.mcp_tools)
    skills_desc = (
        engine._skill_provider.build_skill_catalog_description(engine.skills) if engine._skill_provider else ""
    )
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
        "- Инструменты из секции «Доступные инструменты» уже подключены к ЭТОЙ сессии WebTerm Ops. "
        "Не утверждай, что нет SSH/MCP/Ops, и не путай сессию с Cursor Ask/IDE MCP "
        "(AwaitShell, Task, WebSearch и т.п. сюда не относятся)",
        "- Для удалённых команд на серверах используй native Ops-tools: open_connection / ssh_execute / read_console",
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
        tool_rules.append(
            "- Используй ask_user только когда действительно нужен ввод человека для критического решения"
        )
    if "report" in engine.enabled_tools:
        tool_rules.append("- Используй report для отправки промежуточного отчёта пользователю при длительных задачах")
    if any(name in engine.enabled_tools for name in ("list_materials", "read_material", "run_script_material")):
        tool_rules.append(
            "- Если есть operator materials: list_materials → для script используй run_script_material "
            "(не пиши свой скрипт вместо готового) → проверь side-effects; task_list обновляй через update_material_task"
        )
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
Предпочтительный текстовый формат:
THOUGHT: <твоё рассуждение о том, что делать дальше>
ACTION: tool_name {{"param1": "value1", "param2": "value2"}}

Альтернатива (JSON object, если удобнее модели):
{{"thinking": "<рассуждение>", "tool": "tool_name", "args": {{"param1": "value1"}}}}

Когда задача завершена (больше нет действий), выведи итоговый анализ БЕЗ строки ACTION и без JSON tool-call."""


def _tool_calls_from_iterations(iterations: list[dict] | None) -> list[dict]:
    calls: list[dict] = []
    for item in iterations or []:
        action = str(item.get("action") or "").strip()
        if not action or action == "final_answer":
            continue
        observation = str(item.get("observation") or "")
        calls.append(
            {
                "tool": action,
                "success": bool(observation) and not is_control_plane_text(observation),
            }
        )
    return calls


def _fallback_status(*, exit_reason: str, tool_calls: list[dict] | None, iterations: list[dict] | None = None) -> str:
    evidence = summarize_tool_evidence(tool_calls or _tool_calls_from_iterations(iterations))
    if exit_reason == EXIT_CONTROL_PLANE or evidence["control_plane"]:
        return "❌ Ошибка"
    if exit_reason == EXIT_TIMEOUT:
        return "❌ Ошибка"
    if exit_reason == EXIT_LLM_ERROR:
        if evidence["exec_succeeded"] > 0 or evidence["exec_count"] > 0:
            return "⚠️ Частичный успех"
        return "❌ Ошибка"
    if evidence["exec_succeeded"] > 0:
        return "⚠️ Частичный успех"
    return "❌ Ошибка"


def build_fallback_final_report(
    engine,
    iterations: list[dict],
    *,
    error: str = "",
    exit_reason: str = "",
    tool_calls: list[dict] | None = None,
) -> str:
    if getattr(engine, "_control_plane_blocked", False) or iterations_have_control_plane(iterations):
        return build_control_plane_report(engine, iterations)

    goal = engine.agent.goal or engine.agent.ai_prompt or "Не указана"
    facts = compact_journal_facts(iterations)
    if not facts:
        facts = [f"Итераций в журнале: {len(iterations)}."]
    if error and exit_reason != EXIT_LLM_ERROR:
        facts.append(f"Синтез отчёта: {error[:160]}")

    status = _fallback_status(exit_reason=exit_reason, tool_calls=tool_calls, iterations=iterations)
    if exit_reason == EXIT_LLM_ERROR:
        summary = f"Цель: {str(goal)[:160]}. Агент оборвался на LLM после уже собранных шагов."
        next_step = "Повторить запуск: цикл остановился на вызове модели, не на цели."
    else:
        summary = f"Цель: {str(goal)[:180]}. Ниже факты из журнала, полный LLM-отчёт недоступен."
        next_step = "Проверить вкладку «Шаги», если фактов мало."
    return build_compact_report(
        title=f"{engine.agent.name}: итог по журналу",
        summary=summary,
        facts=facts,
        next_step=next_step,
        status=status,
    )


async def generate_final_report(
    engine,
    history: list[dict],
    iterations: list[dict],
    *,
    exit_reason: str = "",
    tool_calls: list[dict] | None = None,
) -> str:
    if getattr(engine, "_control_plane_blocked", False) or iterations_have_control_plane(iterations):
        return build_control_plane_report(engine, iterations)

    steps_summary = compact_steps_summary(iterations)
    final_answer = ""
    if history:
        final_answer = str(history[-1].get("content") or "")[:400]
    prompt = f"""Ты — технический аналитик. Напиши КОРОТКИЙ финальный отчёт в Markdown.
Язык: русский. Без воды. Максимум {COMPACT_REPORT_MAX_CHARS} символов.
Лучше короче лимита, чем вода. Если не влезает — сначала факты, не вступление.

Данные:
- Агент: {engine.agent.name}
- Цель: {engine.agent.goal or engine.agent.ai_prompt or "Не указана"}
- Итераций: {len(iterations)}
- Журнал:
{steps_summary}
- Итог агента: {final_answer or "Нет данных"}

Жёсткий каркас, ничего лишнего:
1) `# ...` — одна строка, суть результата
2) `> ...` — одно предложение
3) до 5 пунктов `- факт`
4) опционально одна строка `Дальше: ...`
5) `**Статус:** ✅ Успех` / `⚠️ Частичный успех` / `❌ Ошибка`

Запрещено:
- секции `##` (включая «Содержание», «Контекст», «Оценка цели», «Что произошло», «Рекомендации»)
- повторять одно и то же в цитате и в списке
- писать каркас (`#`, `>`, список, статус) больше одного раза
- выдумывать факты, которых нет в журнале"""

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
            execution_context=await engine._execution_context_for("opssummary"),
        ):
            if not is_thinking_chunk(chunk):
                chunks.append(chunk)
        report = "".join(chunks).strip()
        logger.info(
            "agent_run {} final report llm done: chars={}",
            engine.run_record.pk if engine.run_record else "?",
            len(report),
        )
        fallback = build_fallback_final_report(
            engine,
            iterations,
            error="LLM вернул пустой отчёт или запрещённые секции",
            exit_reason=exit_reason,
            tool_calls=tool_calls,
        )
        return coerce_compact_report(report, fallback=fallback)
    except Exception as exc:
        logger.error("Final report generation failed: {}", exc)
        return build_fallback_final_report(
            engine,
            iterations,
            error=str(exc),
            exit_reason=exit_reason,
            tool_calls=tool_calls,
        )
