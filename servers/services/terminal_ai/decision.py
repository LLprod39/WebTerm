"""
Terminal-AI post-command decision workflow.

Owns the recovery and step-by-step LLM calls that decide whether to retry,
skip, ask, continue, add a command, finish, or abort after command output.
"""

from __future__ import annotations

from typing import Any

from loguru import logger
from pydantic import BaseModel

from app.egress_redaction import redact_egress_text
from servers.services.terminal_ai.prompts import build_recovery_prompt, build_step_decision_prompt
from servers.services.terminal_ai.schemas import RecoveryDecision, StepDecision, parse_or_repair


async def _stream_decision(
    *,
    prompt: str,
    purpose: str,
    schema: type[BaseModel],
    fallback: dict[str, Any],
    warning_label: str,
    semaphore=None,
    llm_factory=None,
    max_chars: int,
) -> dict[str, Any]:
    from app.core.llm import LLMProvider

    factory = llm_factory or LLMProvider
    llm = factory()
    out = ""

    async def _collect() -> None:
        nonlocal out
        async for chunk in llm.stream_chat(
            prompt,
            model="auto",
            purpose=purpose,
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

    decision, err = parse_or_repair(out, schema)
    if decision is None:
        logger.warning("%s parse failed: %s, output: %.200s", warning_label, err, redact_egress_text(out).text)
        return fallback
    return decision.model_dump()


async def decide_recovery(
    *,
    cmd: str,
    exit_code: int,
    output: str,
    remaining_cmds: list[str],
    user_reply: str | None = None,
    semaphore=None,
    llm_factory=None,
) -> dict[str, Any]:
    """Decide what to do after a command failure."""
    prompt = build_recovery_prompt(
        cmd=cmd,
        exit_code=exit_code,
        output=output or "",
        remaining_cmds=remaining_cmds or [],
        user_reply=user_reply,
    )
    return await _stream_decision(
        prompt=prompt,
        purpose="terminal_recovery",
        schema=RecoveryDecision,
        fallback={"action": "skip", "why": "Не удалось разобрать ответ LLM — пропускаю команду"},
        warning_label="decide_recovery",
        semaphore=semaphore,
        llm_factory=llm_factory,
        max_chars=3000,
    )


async def decide_step_next(
    *,
    user_goal: str,
    last_cmd: str,
    exit_code: int,
    output: str,
    remaining_cmds: list[str],
    user_reply: str | None = None,
    semaphore=None,
    llm_factory=None,
) -> dict[str, Any]:
    """Decide the next step after a command in step-by-step mode."""
    prompt = build_step_decision_prompt(
        user_goal=user_goal,
        last_cmd=last_cmd,
        exit_code=exit_code,
        output=output or "",
        remaining_cmds=remaining_cmds or [],
        user_reply=user_reply,
    )
    return await _stream_decision(
        prompt=prompt,
        purpose="terminal_step_decision",
        schema=StepDecision,
        fallback={"action": "continue"},
        warning_label="decide_step_next",
        semaphore=semaphore,
        llm_factory=llm_factory,
        max_chars=5000,
    )
