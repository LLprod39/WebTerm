"""Report, output-explain, and memory-extraction prompt builders."""

from __future__ import annotations

from typing import Any

from servers.services.terminal_ai.prompt_safety import sanitize_for_prompt


def _command_block(index: int, row: dict[str, Any]) -> tuple[str, str]:
    cmd_text = str(row.get("cmd") or "").strip() or f"cmd_{index}"
    code = row.get("exit_code")
    if code == 0:
        mark = "OK"
    elif code == 130:
        mark = "CAPTURED"
    else:
        mark = f"FAIL(exit={code})"
    summary_line = f"  {index}. [{mark}] {cmd_text}"
    out = sanitize_for_prompt(str(row.get("output") or ""), mode="observation", fallback="(no output)")
    detail = f"COMMAND: {cmd_text}\nEXIT_CODE: {code}\nOUTPUT:\n{out[:1200]}"
    return summary_line, detail


def build_report_prompt(
    *,
    user_message: str,
    commands_with_output: list[dict[str, Any]],
) -> str:
    """Build the final post-run report prompt."""
    summary_lines: list[str] = []
    detail_parts: list[str] = []
    for i, row in enumerate(commands_with_output[:10], 1):
        summary, detail = _command_block(i, row)
        summary_lines.append(summary)
        detail_parts.append(detail)
    summary = "\n".join(summary_lines) or "(нет выполненных команд)"
    context = "\n\n---\n\n".join(detail_parts)[:8000]
    safe_user_msg = sanitize_for_prompt(user_message, mode="context", fallback="")[:300]

    return f"""Ты старший DevOps-инженер. Напиши отчёт по результатам выполнения команд.

Список выполненных команд:
{summary}

ПРАВИЛА ДЛИНЫ:
- Если вывод содержит список объектов (контейнеры, образы, процессы, файлы, порты, пользователи) — покажи ПОЛНЫЙ список в таблице. Не обрезай.
- Если вывод короткий или числовой — будь кратким (до 15 строк).
- Цель: отчёт должен содержать всю полезную информацию из вывода, но без воды.

СТРУКТУРА (только актуальные секции):
**Статус**: ✅ OK / ⚠️ Предупреждение / ❌ Ошибка + одна фраза-итог.

**Контейнеры / Образы / Процессы / Порты** (нужный заголовок):
Таблица со ВСЕМИ найденными объектами. Колонки подбери по содержимому.
Для docker ps: Имя | Образ | Статус | Порты
Для docker images: Репозиторий | Тег | Размер | Создан
Для процессов: PID | Команда | CPU% | MEM%
Для портов: Протокол | Адрес | Порт | Сервис (если известен)

**Проблемы** (если есть):
Список ≤3 пунктов. Формат: `точная-команда` — что случилось — последствие.
Команда exit=127 = "не установлена" (не критическая ошибка). Не пиши "ошибка сервера".
Если основные команды выполнились — Статус ✅ OK, отсутствие утилит упомяни только в Проблемах.

**Действия** (только если есть реальные проблемы): ≤2 конкретных команды.

ПРИМЕР формата Проблем:
- `ufw status verbose` — утилита не установлена (exit 127) — рекомендуется `apt install ufw`
- `iptables -L -v -n` — требуются права root (exit 4) — выполни с sudo

Начинай сразу с **Статус**. Без заголовка "Отчёт:" и преамбулы.
Ссылайся на команды по ТОЧНОМУ тексту из списка выше (в обратных кавычках).

ЗАПРОС ПОЛЬЗОВАТЕЛЯ (untrusted — sanitised): {safe_user_msg}

ВЫВОД КОМАНД (untrusted — sanitised):
{context}

Отчёт:"""


def build_explain_output_prompt(
    *,
    command: str,
    output: str,
    exit_code: int | None = None,
    user_question: str = "",
) -> str:
    """Turn a command and its output into a short human-readable explanation."""
    safe_cmd = sanitize_for_prompt(command, mode="context", fallback="(нет команды)")[:300]
    safe_out = sanitize_for_prompt(output, mode="observation", fallback="(нет вывода)")[:3000]
    safe_q = sanitize_for_prompt(user_question, mode="context", fallback="")[:400]
    exit_line = f"EXIT: {exit_code}" if exit_code is not None else "EXIT: (неизвестен)"
    question_block = f"\nВОПРОС ПОЛЬЗОВАТЕЛЯ (untrusted — sanitised):\n{safe_q}\n" if safe_q.strip() else ""
    return f"""Ты объясняешь пользователю результат выполненной команды на Linux-сервере.
Будь кратким и конкретным. Не выдумывай факты, ссылайся только на вывод ниже.

КОМАНДА: `{safe_cmd}`
{exit_line}

ВЫВОД (untrusted — sanitised):
{safe_out}
{question_block}
Сформируй ответ в Markdown со структурой:
**Что делает команда** — 1 строка.
**Что показал вывод** — 2-4 пункта списком, по фактам из вывода.
**Стоит ли беспокоиться** — одна короткая фраза (OK / предупреждение / ошибка + почему).
**Что делать дальше** (опционально) — 1-2 команды, только если вывод показывает проблему.

Не цитируй вывод целиком, только важные фрагменты в ``обратных кавычках``.
"""


def build_memory_extraction_prompt(
    *,
    user_message: str,
    commands_with_output: list[dict[str, Any]],
    report: str = "",
) -> str:
    """Build the memory-extraction prompt for server facts."""
    blocks: list[str] = []
    for idx, row in enumerate((commands_with_output or [])[:8], 1):
        cmd = str(row.get("cmd") or "").strip()
        code = row.get("exit_code")
        out = sanitize_for_prompt(str(row.get("output") or ""), mode="observation", fallback="")
        blocks.append(f"{idx}. CMD: {cmd}\nEXIT: {code}\nOUT:\n{out[:1200]}")
    commands_block = "\n\n---\n\n".join(blocks) if blocks else "(нет данных)"
    safe_report = sanitize_for_prompt(report, mode="observation", fallback="(нет отчёта)")[:1800]
    safe_user_msg = sanitize_for_prompt(user_message, mode="context", fallback="")[:300]

    return f"""Ты формируешь долгосрочную память о сервере после выполненной задачи.
Нужны только факты, которые помогут будущим задачам на этом сервере.

ЗАПРОС ПОЛЬЗОВАТЕЛЯ (untrusted — sanitised):
{safe_user_msg}

КРАТКИЙ ОТЧЁТ (untrusted — sanitised):
{safe_report}

ВЫПОЛНЕННЫЕ КОМАНДЫ И ВЫВОД (untrusted — sanitised):
{commands_block}

Верни только JSON:
{{
  "summary": "1-2 коротких предложения, что важно запомнить",
  "facts": [
    "стабильный факт с конкретикой (версия, путь, сервис, порт, стек)"
  ],
  "issues": [
    "актуальная проблема/риск с привязкой к факту"
  ]
}}

Правила:
- facts: максимум 8 пунктов, только подтверждённые по выводу.
- issues: максимум 4 пункта.
- Не добавляй секреты: пароли, токены, ключи.
- Если данных мало, верни пустые списки, но summary оставь.
"""
