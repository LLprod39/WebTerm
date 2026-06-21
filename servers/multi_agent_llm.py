from __future__ import annotations

from typing import Any

from loguru import logger

from app.core.llm import LLMProvider


async def call_multi_agent_llm_raw(engine: Any, system_prompt: str, user_msg: str) -> str:
    """Call the orchestrator LLM with explicit system and user messages."""
    prompt = f"[SYSTEM]\n{system_prompt}\n\n[USER]\n{user_msg}"
    provider = LLMProvider()
    chunks = []
    try:
        with engine._audit_scope():
            async for chunk in provider.stream_chat(
                prompt,
                model=engine.model_preference,
                specific_model=engine.specific_model,
                purpose="opsplan",
            ):
                chunks.append(chunk)
    except Exception as exc:
        logger.error("Orchestrator LLM call failed: {}", exc)
        raise
    return "".join(chunks)


async def call_multi_agent_llm_history(engine: Any, history: list[dict]) -> str:
    """Call the task LLM with a conversation history list."""
    parts = []
    for msg in history:
        role = msg["role"].upper()
        parts.append(f"[{role}]\n{msg['content']}")
    prompt = "\n\n".join(parts)
    provider = LLMProvider()
    chunks = []
    try:
        with engine._audit_scope():
            async for chunk in provider.stream_chat(
                prompt,
                model=engine.model_preference,
                specific_model=engine.specific_model,
                purpose="ops",
            ):
                chunks.append(chunk)
    except Exception as exc:
        logger.error("Task LLM call failed: {}", exc)
        raise
    return "".join(chunks)
