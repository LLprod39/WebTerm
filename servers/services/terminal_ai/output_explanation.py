"""
Terminal-AI command output explanation workflow.

Turns a command/output pair into a short markdown explanation through the
cheap terminal chat bucket. The WebSocket consumer only handles input
validation and event emission.
"""

from __future__ import annotations

from servers.services.terminal_ai.prompts import build_explain_output_prompt


async def explain_command_output(
    *,
    command: str,
    output: str,
    exit_code: int | None = None,
    user_question: str = "",
    semaphore=None,
    llm_factory=None,
    max_chars: int = 4000,
) -> str:
    from app.core.llm import LLMProvider

    factory = llm_factory or LLMProvider
    prompt = build_explain_output_prompt(
        command=command,
        output=output,
        exit_code=exit_code,
        user_question=user_question,
    )
    llm = factory()
    text = ""

    async def _collect() -> None:
        nonlocal text
        async for chunk in llm.stream_chat(prompt, model="auto", purpose="terminal_chat"):
            text += chunk
            if len(text) > max_chars:
                break

    if semaphore is None:
        await _collect()
    else:
        async with semaphore:
            await _collect()
    return text.strip()
