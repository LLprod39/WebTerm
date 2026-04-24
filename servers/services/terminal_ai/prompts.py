"""
Prompt builders for terminal AI LLM calls (F1-5 / F1-1 / F1-2).

All untrusted text (terminal tail, command output, DB-sourced knowledge,
chat history, user message fragments injected back via "user reply")
MUST flow through :func:`sanitize_for_prompt` before being embedded
into a prompt template. This blocks prompt-injection vectors and redacts
secrets using the same ``app.agent_kernel.memory.redaction`` layer that
the main agent runtime uses — closing the ``P1``/``P4`` gap from the
audit.

Trusted text (role instructions, hard-coded rules, JSON schema fences)
is embedded verbatim.

The module is pure Python and has no Django / WebSocket dependencies, so
every builder can be exercised in isolation from the test suite.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from app.agent_kernel.memory.redaction import (
    sanitize_observation_text,
    sanitize_prompt_context_text,
)

# ---------------------------------------------------------------------------
# Sanitisation
# ---------------------------------------------------------------------------

_EMPTY_PLACEHOLDER = "(пусто)"
_HISTORY_PLACEHOLDER = "(начало диалога)"


def sanitize_for_prompt(text: str | None, *, mode: str = "context", fallback: str | None = None) -> str:
    """Redact secrets + neutralise prompt-injection in untrusted text.

    ``mode``:
      - ``"context"``: prompt-context rails (role/system line neutralisation
        in addition to observation-level filtering). Use for DB knowledge,
        rules, recent history.
      - ``"observation"``: observation rails only. Use for raw command
        output / terminal tail.

    ``fallback`` is returned verbatim when the sanitized text is empty.
    """
    raw = "" if text is None else str(text)
    if not raw.strip():
        return fallback if fallback is not None else ""
    sanitized = sanitize_observation_text(raw).text if mode == "observation" else sanitize_prompt_context_text(raw).text
    return sanitized if sanitized.strip() else (fallback if fallback is not None else "")


# ---------------------------------------------------------------------------
# Helpers shared with the consumer (F1-5 extraction target)
# ---------------------------------------------------------------------------


def build_unavailable_tools_block(unavailable_cmds: Iterable[str] | None) -> str:
    """Warn the LLM about CLI utilities that returned exit=127 this session."""
    unavail = sorted({str(c).strip() for c in (unavailable_cmds or []) if str(c).strip()})
    if not unavail:
        return ""
    tools_list = ", ".join(f"`{t}`" for t in unavail)
    return f"""
═══ НЕДОСТУПНЫЕ ИНСТРУМЕНТЫ (НЕ ИСПОЛЬЗОВАТЬ) ═══
На этом сервере НЕ установлены (exit=127 при попытке): {tools_list}
→ Используй ТОЛЬКО доступные альтернативы:
   • вместо `netstat` → `ss`
   • вместо `ufw` → `iptables` (если есть права) или просто сообщи что не установлен
   • вместо `ifconfig` → `ip addr`
   • вместо `service` → `systemctl`
"""


def build_history_text(history: list[dict] | None) -> str:
    """Render recent chat turns; untrusted text is sanitised."""
    lines: list[str] = []
    for turn in (history or [])[:-1]:
        role = str(turn.get("role") or "user")
        text_raw = str(turn.get("text") or "")[:600]
        text = sanitize_for_prompt(text_raw, mode="context", fallback="(скрыто)")
        prefix = "Пользователь" if role == "user" else "Ассистент"
        lines.append(f"[{prefix}]: {text}")
    return "\n".join(lines) if lines else _HISTORY_PLACEHOLDER


def build_execution_mode_block(execution_mode: str) -> str:
    """Instructions for the planner about the current execution mode."""
    if execution_mode == "auto":
        return """
- execution_mode=auto: выбери execution_mode самостоятельно:
  • step — если задача рискованная/неоднозначная/требует проверки после каждого шага
  • fast — если задача линейная и предсказуемая
"""
    return f"""
- execution_mode фиксирован пользователем: используй {execution_mode} (не меняй).
"""


def build_chat_mode_block(chat_mode: str) -> str:
    """Ask vs Agent mode instruction block."""
    if chat_mode == "ask":
        return """
РЕЖИМ ЧАТА: ASK
- Пользователь не хочет автозапуск команд.
- Если для задачи нужны команды на сервере, всё равно используй mode=execute, но сформируй это как предложения/шаги для пользователя.
- assistant_text должен коротко объяснить, что команды ниже предложены для ручного запуска.
"""
    return """
РЕЖИМ ЧАТА: AGENT
- Если задача требует действий на сервере, предпочитай mode=execute.
- Команды будут выполняться автоматически, кроме опасных действий, которые потребуют подтверждения.
"""


# ---------------------------------------------------------------------------
# Planner (P1 of the audit: sanitized terminal_tail/history/rules_context)
# ---------------------------------------------------------------------------


def build_dry_run_block(dry_run: bool) -> str:
    """A5: prompt block that warns the model about dry-run mode.

    Kept as a small standalone helper so tests can assert the wording
    precisely, and so callers that don't need dry-run pay zero prompt
    tokens for the feature.
    """
    if not dry_run:
        return ""
    return (
        "\n═══ РЕЖИМ DRY-RUN ═══\n"
        "Команды НЕ БУДУТ выполнены на сервере. Это предварительный просмотр плана.\n"
        "- Генерируй план как обычно: выбирай safe команды, честно помечай опасные.\n"
        "- НЕ пропускай обязательные preflight-команды — они тоже должны быть в плане,\n"
        "  даже если они 'просто читают' — пользователь хочет видеть полный набор шагов.\n"
        "- В assistant_text скажи одной фразой: 'Dry-run: покажу план без запуска'.\n"
    )


def _planner_system_prompt(
    *,
    chat_mode_block: str,
    execution_mode: str,
    exec_mode_block: str,
    dry_run_block: str,
    unavail_block: str,
    safe_rules: str,
) -> str:
    """Stable system-level instructions for the planner LLM call.

    This portion changes only when server rules, chat-mode or exec-mode
    change — which happens rarely within the same session.  Separating it
    enables provider-level prompt caching (Anthropic ``cache_control``,
    OpenAI automatic prefix caching, Gemini ``system_instruction``).
    """
    return f"""Ты умный DevOps/SSH ассистент в составе платформы управления серверами.
Ты ведёшь диалог с пользователем и имеешь доступ к SSH-терминалу сервера.

{chat_mode_block}

РЕЖИМ ВЫПОЛНЕНИЯ: {execution_mode}
- auto: агент сам выбирает step/fast для этого запуска.
- step: выдай короткий стартовый план (обычно 1-3 команды), дальше план будет адаптироваться после каждого шага.
- fast: можно выдать полный линейный план сразу (до 6 команд).
{exec_mode_block}
{dry_run_block}
═══ ТВОЯ ЗАДАЧА ═══
Самостоятельно решить, что делать с запросом пользователя, выбрав один из режимов:
  • mode=answer  — ответить, объяснить, проконсультировать (БЕЗ команд)
  • mode=execute — выполнить команды на сервере
  • mode=ask     — задать уточняющий вопрос пользователю

═══ ПРАВИЛА ВЫБОРА РЕЖИМА ═══
→ Общие вопросы, "что такое X", "как работает Y", теория → mode=answer
→ Приветствия, благодарности, короткие реплики → mode=answer (кратко)
→ Нужно что-то проверить/сделать/настроить на сервере → mode=execute
→ Пользователь хочет одновременно объяснения и действий → mode=execute (объяснение в assistant_text)
→ Запрос слишком неоднозначен, нужна конкретика → mode=ask
{unavail_block}
═══ КРИТИЧЕСКИЕ ПРАВИЛА ДЛЯ КОМАНД (только mode=execute) ═══
1. НИКОГДА не используй команды с бесконечным выводом — они зависнут:
   ✗ tail -f   → ✓ tail -n 100
   ✗ journalctl -f   → ✓ journalctl -n 100 --no-pager
   ✗ docker logs -f  → ✓ docker logs --tail=100
   ✗ watch cmd       → ✓ разовая команда
   ✗ top/htop        → ✓ ps aux --sort=-%cpu | head -20
   ✗ ping host       → ✓ ping -c 4 host
2. Используй --no-pager для journalctl, systemctl show, git log и т.д.
3. Максимум 6 команд. Начинай с диагностики, потом действия.
4. Разрушительные команды (rm -rf, drop, truncate) — только если явно попросили + нужно подтверждение.
5. Для редактирования файлов: используй sed -i, awk, tee или heredoc (cat > file << 'EOF').

═══ ФОРМАТ ОТВЕТА (ТОЛЬКО JSON, без markdown вокруг) ═══
{{
  "execution_mode": "step" | "fast",
  "mode": "answer" | "execute" | "ask",
  "assistant_text": "текст пользователю (Markdown, всегда заполнен)",
  "commands": [{{"cmd": "команда", "why": "зачем эта команда"}}]
}}
Поле execution_mode всегда обязательно.
Поле commands — только для mode=execute. Для остальных режимов — [].

═══ КОНТЕКСТ СЕРВЕРА/ПОЛИТИКИ (untrusted — sanitised) ═══
{safe_rules}"""


def _planner_user_prompt(
    *,
    safe_history: str,
    safe_tail: str,
    safe_user_msg: str,
) -> str:
    """Per-request user message for the planner LLM call."""
    return f"""═══ ИСТОРИЯ ДИАЛОГА (untrusted — sanitised) ═══
{safe_history}

═══ ПОСЛЕДНИЙ ВЫВОД ТЕРМИНАЛА (untrusted — sanitised) ═══
{safe_tail}

═══ ТЕКУЩИЙ ЗАПРОС ПОЛЬЗОВАТЕЛЯ (untrusted — sanitised) ═══
{safe_user_msg}

Верни только JSON."""


def _planner_common_args(
    *,
    user_message: str,
    rules_context: str,
    terminal_tail: str,
    history: list[dict] | None,
    unavailable_cmds: Iterable[str] | None,
    chat_mode: str,
    execution_mode: str,
    dry_run: bool = False,
) -> tuple[str, str]:
    """Shared helper: returns ``(system_prompt, user_prompt)``."""
    chat_mode_block = build_chat_mode_block(chat_mode)
    exec_mode_block = build_execution_mode_block(execution_mode)
    unavail_block = build_unavailable_tools_block(unavailable_cmds)
    dry_run_block = build_dry_run_block(dry_run)

    safe_rules = sanitize_for_prompt(rules_context, mode="context", fallback="(нет)")
    safe_tail = sanitize_for_prompt(terminal_tail, mode="observation", fallback=_EMPTY_PLACEHOLDER)
    safe_user_msg = sanitize_for_prompt(user_message, mode="context", fallback="")
    safe_history = build_history_text(history)

    system = _planner_system_prompt(
        chat_mode_block=chat_mode_block,
        execution_mode=execution_mode,
        exec_mode_block=exec_mode_block,
        dry_run_block=dry_run_block,
        unavail_block=unavail_block,
        safe_rules=safe_rules,
    )
    user = _planner_user_prompt(
        safe_history=safe_history,
        safe_tail=safe_tail,
        safe_user_msg=safe_user_msg,
    )
    return system, user


def build_planner_prompt(
    *,
    user_message: str,
    rules_context: str,
    terminal_tail: str,
    history: list[dict] | None,
    unavailable_cmds: Iterable[str] | None,
    chat_mode: str,
    execution_mode: str,
    dry_run: bool = False,
) -> str:
    """Build the planning prompt that produces :class:`TerminalPlanResponse`.

    Returns a single string (system + user concatenated) for backward
    compatibility.  Prefer :func:`build_planner_prompt_parts` for callers
    that can pass ``system_prompt`` to ``LLMProvider.stream_chat``.
    """
    system, user = _planner_common_args(
        user_message=user_message,
        rules_context=rules_context,
        terminal_tail=terminal_tail,
        history=history,
        unavailable_cmds=unavailable_cmds,
        chat_mode=chat_mode,
        execution_mode=execution_mode,
        dry_run=dry_run,
    )
    return f"{system}\n\n{user}"


def build_planner_prompt_parts(
    *,
    user_message: str,
    rules_context: str,
    terminal_tail: str,
    history: list[dict] | None,
    unavailable_cmds: Iterable[str] | None,
    chat_mode: str,
    execution_mode: str,
    dry_run: bool = False,
) -> tuple[str, str]:
    """Build the planning prompt split into ``(system_prompt, user_prompt)``.

    The system portion contains role instructions, mode blocks, command
    rules and server context — content that is **stable within a session**.
    The user portion carries per-request data: chat history, terminal tail,
    and the current user message.

    This split enables provider-level prompt caching:
    - **Anthropic**: ``cache_control`` on the system block.
    - **OpenAI**: automatic prefix caching (stable system message).
    - **Gemini**: ``system_instruction`` parameter.
    """
    return _planner_common_args(
        user_message=user_message,
        rules_context=rules_context,
        terminal_tail=terminal_tail,
        history=history,
        unavailable_cmds=unavailable_cmds,
        chat_mode=chat_mode,
        execution_mode=execution_mode,
        dry_run=dry_run,
    )


# ---------------------------------------------------------------------------
# Recovery (called on non-zero exit)
# ---------------------------------------------------------------------------


def build_recovery_prompt(
    *,
    cmd: str,
    exit_code: int,
    output: str,
    remaining_cmds: list[str],
    user_reply: str | None = None,
) -> str:
    """Build the recovery prompt for :class:`RecoveryDecision`."""
    remaining_text = "\n".join(f"  {i + 1}. {c}" for i, c in enumerate(remaining_cmds[:5])) or "(нет следующих команд)"
    safe_output = sanitize_for_prompt(output, mode="observation", fallback="(нет вывода)")[:2000]
    user_block = ""
    if user_reply:
        safe_reply = sanitize_for_prompt(user_reply, mode="context", fallback="")
        user_block = f"\n\nОтвет пользователя: «{safe_reply}»"

    return f"""Ты DevOps-агент. Команда завершилась с ошибкой. Реши, что делать дальше.

КОМАНДА: {cmd}
КОД ВЫХОДА: {exit_code}
ВЫВОД (untrusted — sanitised):
{safe_output}

СЛЕДУЮЩИЕ КОМАНДЫ В ПЛАНЕ:
{remaining_text}{user_block}

ПРАВИЛА ПРИНЯТИЯ РЕШЕНИЯ:
- exit=127 → команда не найдена → action=retry с альтернативой (ss вместо netstat, ip addr вместо ifconfig, etc.)
- Ошибка прав доступа ("Permission denied", "sudo required", exit=1/126) → action=ask (спросить пользователя нужен ли sudo)
- Явная опечатка или неправильные флаги → action=retry с исправленной командой
- Критическая ошибка, делающая следующие команды бессмысленными → action=abort
- Незначительная ошибка, остальные команды независимы → action=skip
- Неоднозначная ситуация — нужна информация от пользователя → action=ask

ФОРМАТ ОТВЕТА (только JSON, без markdown):
{{
  "action": "retry" | "skip" | "ask" | "abort",
  "cmd": "новая_команда (только для action=retry)",
  "why": "краткое объяснение решения (1-2 предложения)",
  "question": "вопрос пользователю (только для action=ask)"
}}

Верни только JSON."""


# ---------------------------------------------------------------------------
# Step-by-step controller
# ---------------------------------------------------------------------------


def build_step_decision_prompt(
    *,
    user_goal: str,
    last_cmd: str,
    exit_code: int,
    output: str,
    remaining_cmds: list[str],
    user_reply: str | None = None,
) -> str:
    """Build unified post-step prompt for :class:`StepDecision` (F1-9).

    Handles both success (``exit_code==0``) and error branches so that
    step-mode needs a single LLM call per step instead of a separate
    recovery call + step-decide call.
    """
    remaining_text = (
        "\n".join(f"  {i + 1}. {c}" for i, c in enumerate(remaining_cmds[:6]))
        or "(нет оставшихся команд)"
    )
    safe_output = sanitize_for_prompt(output, mode="observation", fallback="(нет вывода)")[:2500]
    safe_goal = sanitize_for_prompt(user_goal, mode="context", fallback="(нет цели)")
    user_reply_block = ""
    if user_reply:
        safe_reply = sanitize_for_prompt(user_reply, mode="context", fallback="")
        user_reply_block = f"\n\nОтвет пользователя: «{safe_reply}»"

    status_hint = (
        "КОМАНДА УСПЕШНА (exit=0)"
        if exit_code == 0
        else ("КОМАНДА ПРЕРВАНА ПОЛЬЗОВАТЕЛЕМ (exit=130)" if exit_code == 130 else f"КОМАНДА УПАЛА (exit={exit_code})")
    )

    return f"""Ты DevOps-агент в режиме step-by-step.
После КАЖДОГО шага ты анализируешь вывод и выбираешь ОДНО действие.
Один шаг = один LLM-вызов. Не делай лишних шагов.

{status_hint}

ЦЕЛЬ ПОЛЬЗОВАТЕЛЯ (untrusted — sanitised):
{safe_goal}

ПОСЛЕДНЯЯ КОМАНДА:
{last_cmd}
EXIT_CODE: {exit_code}
ВЫВОД (untrusted — sanitised):
{safe_output}

ОСТАВШИЙСЯ ПЛАН:
{remaining_text}{user_reply_block}

Выбери одно действие:

ЕСЛИ КОМАНДА УСПЕШНА (exit=0):
- continue: оставить текущий план без изменений
- next: добавить СЛЕДУЮЩУЮ команду перед оставшимся планом (поле next_cmd)
- done: цель уже достигнута по выводу, завершаем
- ask: нужен короткий вопрос к пользователю (поле question)
- abort: критическая ситуация, прерываем выполнение

ЕСЛИ КОМАНДА УПАЛА (exit != 0 и не 130):
- retry: повторить с ИСПРАВЛЕННОЙ командой (поле cmd). Используй для:
  * exit=127 → альтернатива (ss вместо netstat, ip addr вместо ifconfig, systemctl вместо service)
  * явная опечатка или неверные флаги → исправленная команда
- skip: ошибка некритична, остальные команды независимы
- ask: неоднозначно (permission denied, нужен sudo и т.п.) — поле question
- abort: критическая ошибка, делающая следующие команды бессмысленными
- done: несмотря на ошибку, цель уже достигнута (редко)

ЕСЛИ ПРЕРВАНА ПОЛЬЗОВАТЕЛЕМ (exit=130):
- Обычно continue или done (stream-команда отработала как ожидалось)

ПРАВИЛА:
- Максимум 2 retry подряд для одной и той же цели.
- Не предлагай опасные/разрушительные команды без явной необходимости.
- Если данных мало, выбирай ask.
- Если next — next_cmd не должно дублировать команды из оставшегося плана.

ФОРМАТ (только JSON, без markdown):
{{
  "action": "continue" | "next" | "retry" | "skip" | "done" | "ask" | "abort",
  "assistant_text": "краткий комментарий пользователю (опционально)",
  "next_cmd": "команда (только для action=next)",
  "cmd": "исправленная команда (только для action=retry)",
  "why": "зачем этот шаг / решение (1-2 предложения)",
  "question": "вопрос пользователю (только для action=ask)"
}}

Верни только JSON."""


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Explain output (A6)
# ---------------------------------------------------------------------------


def build_explain_output_prompt(
    *,
    command: str,
    output: str,
    exit_code: int | None = None,
    user_question: str = "",
) -> str:
    """A6: short prompt that turns a command + its output into a
    human-readable explanation. Output MUST be treated as untrusted and
    therefore routed through the observation-rails sanitizer.

    The prompt is deliberately tight so it fits into the cheap
    ``terminal_chat`` bucket and finishes quickly.
    """
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


# ---------------------------------------------------------------------------
# Memory extraction (P2/P4)
# ---------------------------------------------------------------------------


def build_memory_extraction_prompt(
    *,
    user_message: str,
    commands_with_output: list[dict[str, Any]],
    report: str = "",
) -> str:
    """Build the memory-extraction prompt for :class:`MemoryExtraction`."""
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
