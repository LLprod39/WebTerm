"""
Terminal-AI report generation workflow.

Keeps LLM report streaming outside the WebSocket consumer while reusing the
pure fallback/status helpers from ``reporter.py``.
"""

from __future__ import annotations

from typing import Any

from loguru import logger

from servers.services.terminal_ai.prompts import build_report_prompt
from servers.services.terminal_ai.reporter import build_fallback_report


async def make_ai_report(
    user_message: str,
    commands_with_output: list[dict[str, Any]],
    *,
    semaphore=None,
    llm_factory=None,
    max_chars: int = 12000,
) -> str:
    from app.core.llm import LLMProvider

    factory = llm_factory or LLMProvider
    prompt = build_report_prompt(
        user_message=user_message,
        commands_with_output=commands_with_output or [],
    )
    llm = factory()
    out = ""

    async def _collect() -> None:
        nonlocal out
        async for chunk in llm.stream_chat(prompt, model="auto", purpose="terminal_report"):
            out += chunk
            if len(out) > max_chars:
                break

    if semaphore is None:
        await _collect()
    else:
        async with semaphore:
            await _collect()
    return (out or "").strip()


async def generate_ai_report_text(
    user_message: str,
    done_items: list[dict[str, Any]],
    *,
    semaphore=None,
    llm_factory=None,
) -> str:
    done_with_output = [item for item in done_items if (item.get("output") or "").strip()]
    report = ""
    if done_with_output:
        try:
            report = (
                await make_ai_report(
                    user_message,
                    done_with_output,
                    semaphore=semaphore,
                    llm_factory=llm_factory,
                )
            ).strip()
        except Exception as exc:
            logger.warning("AI report generation failed: %s", exc)
    return report or build_fallback_report(done_items)
