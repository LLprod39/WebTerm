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

from servers.services.terminal_ai.prompt_reporting import (
    build_explain_output_prompt,
    build_memory_extraction_prompt,
    build_report_prompt,
)
from servers.services.terminal_ai.prompt_safety import (
    EMPTY_PLACEHOLDER as _EMPTY_PLACEHOLDER,
)
from servers.services.terminal_ai.prompt_safety import (
    HISTORY_PLACEHOLDER as _HISTORY_PLACEHOLDER,
)
from servers.services.terminal_ai.prompt_safety import (
    sanitize_for_prompt,
)

__all__ = [
    "build_chat_mode_block",
    "build_dry_run_block",
    "build_execution_mode_block",
    "build_explain_output_prompt",
    "build_history_text",
    "build_memory_extraction_prompt",
    "build_planner_prompt",
    "build_planner_prompt_parts",
    "build_recovery_prompt",
    "build_report_prompt",
    "build_step_decision_prompt",
    "build_unavailable_tools_block",
    "sanitize_for_prompt",
]

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
- fast: можно выдать полный линейный план сразу (до 10 команд; hard max 12).
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
→ Сложная multi-step ops (инцидент, root cause + fix + verify, migrate/deploy, multi-service):
  если execution_mode=fast — НЕ пытайся «влезть» в короткий линейный план.
  Верни mode=ask с assistant_text: предложи переключиться на Nova (agent) или сузить цель.
  В mode=ask поле commands должно быть [].
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
3. Максимум 10 команд (hard max 12). Начинай с диагностики, потом действия.
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
