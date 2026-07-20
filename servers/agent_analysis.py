from __future__ import annotations

from typing import TYPE_CHECKING, Any

from asgiref.sync import sync_to_async as _s2a
from loguru import logger

from app.agent_kernel import skill_provider_registry
from app.core.llm import LLMProvider, is_thinking_chunk
from servers.agent_inputs import build_agent_materials_prompt

if TYPE_CHECKING:
    from servers.models import Server, ServerAgent


def _sync_to_async(func, thread_sensitive: bool = False):
    return _s2a(func, thread_sensitive=thread_sensitive)


def _build_analysis_prompt(
    *,
    agent: ServerAgent,
    server: Server,
    outputs: list[dict[str, Any]],
    template: dict[str, Any] | None,
    skills_desc: str,
    skill_errors: list[str],
) -> str:
    prompt_parts = [
        f"# Agent: {agent.name}",
        f"Server: **{server.name}** ({server.host})",
        "",
    ]
    system_prompt = (template or {}).get("ai_prompt", "")
    if system_prompt:
        prompt_parts.extend([system_prompt, ""])
    if agent.ai_prompt:
        prompt_parts.extend([f"Additional instructions: {agent.ai_prompt}", ""])

    materials_prompt = build_agent_materials_prompt(agent.input_artifacts)
    if materials_prompt:
        prompt_parts.extend([materials_prompt, ""])
    if skills_desc or skill_errors:
        prompt_parts.append("## Attached skills")
        prompt_parts.append(skills_desc or "- Skills не подключены")
        if skill_errors:
            prompt_parts.append("Недоступные skills:")
            prompt_parts.extend(f"- {item}" for item in skill_errors)
        prompt_parts.append("")

    prompt_parts.append("## Command outputs:\n")
    for index, out in enumerate(outputs, 1):
        prompt_parts.append(f"### Command {index}: `{out['cmd']}`")
        prompt_parts.append(f"Exit code: {out['exit_code']}")
        if out["stdout"]:
            prompt_parts.append(f"```\n{out['stdout'][:3000]}\n```")
        if out["stderr"]:
            prompt_parts.append(f"Stderr: `{out['stderr'][:500]}`")
        prompt_parts.append("")

    prompt_parts.extend(
        [
            "---",
            "Предоставь краткий анализ в формате **Markdown** на русском языке:",
            "1. **Резюме** — 1-2 предложения об общем состоянии",
            "2. **Обнаружения** — ключевые проблемы, отсортированные по серьёзности",
            "3. **Рекомендации** — конкретные практические шаги",
            "4. **Уровень риска** — Низкий / Средний / Высокий / Критический",
            "",
            "Будь конкретным и практичным. Отвечай на русском языке.",
        ]
    )
    return "\n".join(prompt_parts)


async def get_ai_analysis(
    agent: ServerAgent,
    server: Server,
    outputs: list[dict[str, Any]],
    *,
    template: dict[str, Any] | None,
) -> str:
    skills, skill_errors = await _sync_to_async(
        lambda: skill_provider_registry.resolve_skills(list(agent.skill_slugs or [])),
        thread_sensitive=True,
    )()
    skill_provider = skill_provider_registry.get()
    skills_desc = skill_provider.build_skill_catalog_description(skills) if skill_provider else ""
    full_prompt = _build_analysis_prompt(
        agent=agent,
        server=server,
        outputs=outputs,
        template=template,
        skills_desc=skills_desc,
        skill_errors=skill_errors,
    )

    try:
        chunks = []
        async for chunk in LLMProvider().stream_chat(full_prompt, model="auto"):
            if not is_thinking_chunk(chunk):
                chunks.append(chunk)
        return "".join(chunks)
    except Exception as exc:
        logger.error("AI analysis failed for agent '{}': {}", agent.name, exc)
        return f"AI analysis failed: {exc}"
