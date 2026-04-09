"""
Terminal AI service — shared prompt templates and helper utilities.

P1-5: First step of consumers.py modularisation.

Extracts prompt-construction logic and stateless helpers so they can be:
- unit-tested independently
- reused in future non-WebSocket AI endpoints
- adjusted without touching the WebSocket consumer
"""
from __future__ import annotations

import json
from typing import Any


# ---------------------------------------------------------------------------
# Prompt helpers
# ---------------------------------------------------------------------------

def build_unavailable_tools_block(unavailable_cmds: set[str] | None) -> str:
    """Build a prompt section warning the LLM about unavailable CLI tools."""
    unavail = sorted(unavailable_cmds or set())
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
    """Convert conversation history entries into prompt text."""
    history_lines: list[str] = []
    for h in (history or [])[:-1]:
        role = str(h.get("role") or "user")
        text = str(h.get("text") or "")[:600]
        prefix = "Пользователь" if role == "user" else "Ассистент"
        history_lines.append(f"[{prefix}]: {text}")
    return "\n".join(history_lines) if history_lines else "(начало диалога)"


def build_execution_mode_block(execution_mode: str) -> str:
    """Build the execution_mode instruction for the prompt."""
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
    """Build the chat-mode instruction (ask vs agent)."""
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
# Report helpers
# ---------------------------------------------------------------------------

def compute_report_status(done_items: list[dict[str, Any]]) -> str:
    """Compute summary status from a list of executed command results."""
    codes = [item.get("exit_code") for item in done_items]
    non_captured = [c for c in codes if c != 130]
    if non_captured and all(c == 0 for c in non_captured if c is not None):
        return "ok"
    if any(c not in (None, 0, 130) for c in codes):
        ok_count = sum(1 for c in codes if c in (0, 130))
        return "error" if ok_count < len(codes) / 2 else "warning"
    return "warning"


def build_fallback_report(done_items: list[dict[str, Any]]) -> str:
    """Build a fallback report when AI analysis fails."""
    codes = [item.get("exit_code") for item in done_items]
    all_ok = all(code == 0 for code in codes if code is not None)
    if all_ok:
        return (
            "Команды выполнены успешно (код выхода 0). Вывод смотрите в консоли слева. "
            "Краткий анализ по выводу сформировать не удалось — попробуйте запрос ещё раз или проверьте логи вручную."
        )
    return (
        "Команды выполнены. Коды выхода: "
        + ", ".join(str(code) for code in codes)
        + ". Вывод в консоли слева. Для анализа проверьте вывод вручную."
    )


def sanitize_memory_line(text: str) -> str:
    """Clean and truncate a line for memory storage."""
    line = str(text or "").replace("\n", " ").replace("\r", " ").strip()
    return line[:400]


def extract_json_object(text: str) -> dict:
    """Robustly extract the first JSON object from LLM output text.

    Handles markdown fences, leading text, and trailing garbage.
    """
    if not text:
        return {}

    # Strip markdown fences
    cleaned = text.strip()
    if cleaned.startswith("```"):
        first_nl = cleaned.index("\n") if "\n" in cleaned else len(cleaned)
        cleaned = cleaned[first_nl + 1 :]
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3]
    cleaned = cleaned.strip()

    # Try raw parse first
    try:
        return json.loads(cleaned)
    except (json.JSONDecodeError, ValueError):
        pass

    # Find first '{' and use raw_decode
    brace_idx = cleaned.find("{")
    if brace_idx == -1:
        return {}

    try:
        decoder = json.JSONDecoder()
        obj, _ = decoder.raw_decode(cleaned, brace_idx)
        if isinstance(obj, dict):
            return obj
    except (json.JSONDecodeError, ValueError):
        pass

    return {}
