"""
Terminal-AI durable memory extraction workflow.

This module owns the LLM prompt execution and extracted-memory cleanup that
used to live in ``SSHTerminalConsumer``. The consumer still decides when to
spawn background work, but the extraction/save body is reusable and
unit-testable without a WebSocket instance.
"""

from __future__ import annotations

from typing import Any

from loguru import logger

from servers.services.terminal_ai.memory import sanitize_memory_line, save_server_profile
from servers.services.terminal_ai.prompts import build_memory_extraction_prompt
from servers.services.terminal_ai.schemas import MemoryExtraction, parse_or_repair


def _clean_memory_list(items: list[str], *, limit: int) -> list[str]:
    seen: set[str] = set()
    cleaned: list[str] = []
    for item in items or []:
        line = sanitize_memory_line(str(item or ""))
        if not line:
            continue
        key = line.lower()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(line)
        if len(cleaned) >= limit:
            break
    return cleaned


async def extract_server_memory(
    *,
    user_message: str,
    commands_with_output: list[dict[str, Any]],
    report: str = "",
    semaphore=None,
    llm_factory=None,
    max_chars: int = 7000,
) -> dict[str, Any]:
    """
    Build concise durable server context from a terminal AI run.

    Untrusted output/report/user_message is sanitized inside
    ``build_memory_extraction_prompt`` before embedding into the prompt. The
    response is validated with ``MemoryExtraction`` before any field is
    returned to the caller.
    """
    from app.core.llm import LLMProvider

    factory = llm_factory or LLMProvider
    prompt = build_memory_extraction_prompt(
        user_message=user_message,
        commands_with_output=commands_with_output or [],
        report=report,
    )
    llm = factory()
    out = ""

    async def _collect() -> None:
        nonlocal out
        async for chunk in llm.stream_chat(prompt, model="auto", purpose="memory_extraction"):
            out += chunk
            if len(out) > max_chars:
                break

    if semaphore is None:
        await _collect()
    else:
        async with semaphore:
            await _collect()

    extraction, err = parse_or_repair(out, MemoryExtraction)
    if extraction is None:
        logger.warning("extract_server_memory parse failed: %s, output: %.200s", err, out)
        return {"summary": "", "facts": [], "issues": []}

    return {
        "summary": sanitize_memory_line(extraction.summary),
        "facts": _clean_memory_list(extraction.facts, limit=8),
        "issues": _clean_memory_list(extraction.issues, limit=4),
    }


async def save_extracted_server_memory(
    *,
    user_id: int,
    server_id: int,
    memory_obj: dict[str, Any],
) -> dict[str, Any] | None:
    """Persist extracted memory when it contains durable content."""
    summary = str((memory_obj or {}).get("summary") or "").strip()
    facts = list((memory_obj or {}).get("facts") or [])
    issues = list((memory_obj or {}).get("issues") or [])
    if not summary and not facts and not issues:
        return None
    return await save_server_profile(
        user_id=user_id,
        server_id=server_id,
        summary=summary,
        facts=facts,
        issues=issues,
    )


async def run_memory_extraction(
    *,
    user_message: str,
    commands_with_output: list[dict[str, Any]],
    report: str,
    user_id: int,
    server_id: int,
    semaphore=None,
    llm_factory=None,
) -> dict[str, Any] | None:
    """Extract durable server memory and persist it if anything useful exists."""
    memory_obj = await extract_server_memory(
        user_message=user_message,
        commands_with_output=commands_with_output,
        report=report,
        semaphore=semaphore,
        llm_factory=llm_factory,
    )
    return await save_extracted_server_memory(
        user_id=user_id,
        server_id=server_id,
        memory_obj=memory_obj,
    )
