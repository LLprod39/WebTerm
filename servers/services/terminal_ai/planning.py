"""
Terminal-AI command planning workflow.

The WebSocket consumer supplies session context and execution settings; this
module owns prompt construction, LLM streaming, schema validation, and the
legacy JSON fallback used when the model returns slightly malformed data.
"""

from __future__ import annotations

import json
import re
from typing import Any

from loguru import logger

from app.egress_redaction import redact_egress_text
from servers.services.terminal_ai.prompts import build_planner_prompt_parts
from servers.services.terminal_ai.schemas import TerminalPlanResponse, parse_or_repair


def extract_json_object(text: str) -> dict[str, Any]:
    """Extract a JSON object from raw model text, matching legacy consumer behavior."""
    cleaned = (text or "").strip()
    if "```" in cleaned:
        cleaned = re.sub(r"```(?:json)?", "", cleaned, flags=re.IGNORECASE).replace("```", "").strip()
    start = cleaned.find("{")
    if start < 0:
        raise ValueError(f"AI не вернул JSON: {cleaned[:400]}")
    decoder = json.JSONDecoder()
    obj, _ = decoder.raw_decode(cleaned[start:])
    if not isinstance(obj, dict):
        raise ValueError("AI JSON должен быть объектом")
    return obj


def _planner_fallback(execution_mode: str) -> dict[str, Any]:
    return {
        "mode": "answer",
        "execution_mode": execution_mode if execution_mode != "auto" else "step",
        "assistant_text": "Не удалось разобрать ответ модели. Попробуйте переформулировать запрос.",
        "commands": [],
    }


def _normalize_plan_payload(plan: TerminalPlanResponse) -> dict[str, Any]:
    payload = plan.model_dump()
    payload["commands"] = [
        {
            "cmd": command["cmd"],
            "why": command.get("why", ""),
            "exec_mode": command.get("exec_mode", "pty"),
        }
        for command in payload.get("commands", [])
    ]
    return payload


async def plan_terminal_commands(
    *,
    user_message: str,
    rules_context: str,
    terminal_tail: str,
    history: list[dict] | None = None,
    unavailable_cmds: set[str] | None = None,
    chat_mode: str = "agent",
    execution_mode: str = "step",
    dry_run: bool = False,
    semaphore=None,
    llm_factory=None,
    max_chars: int = 20000,
) -> dict[str, Any]:
    """
    Ask the LLM to choose answer/ask/execute mode and planned commands.

    Untrusted session inputs are sanitized by ``build_planner_prompt_parts``.
    The preferred path validates against ``TerminalPlanResponse``; when the
    schema fails, the legacy object extraction fallback is retained for
    backwards compatibility with older model responses.
    """
    from app.core.llm import LLMProvider

    factory = llm_factory or LLMProvider
    system_prompt, user_prompt = build_planner_prompt_parts(
        user_message=user_message,
        rules_context=rules_context,
        terminal_tail=terminal_tail,
        history=history,
        unavailable_cmds=unavailable_cmds,
        chat_mode=chat_mode,
        execution_mode=execution_mode,
        dry_run=dry_run,
    )
    llm = factory()
    out = ""

    async def _collect() -> None:
        nonlocal out
        async for chunk in llm.stream_chat(
            user_prompt,
            model="auto",
            purpose="terminal_planning",
            system_prompt=system_prompt,
            json_mode=True,
        ):
            out += chunk
            if len(out) > max_chars:
                break

    if semaphore is None:
        await _collect()
    else:
        async with semaphore:
            await _collect()

    if (out or "").strip().lower().startswith("error:"):
        raise ValueError(out.strip())

    plan, err = parse_or_repair(out, TerminalPlanResponse)
    if plan is not None:
        return _normalize_plan_payload(plan)

    logger.warning("plan_terminal_commands parse failed: %s, output: %.200s", err, redact_egress_text(out).text)
    try:
        return extract_json_object(out)
    except Exception:
        return _planner_fallback(execution_mode)
