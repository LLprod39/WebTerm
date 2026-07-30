from __future__ import annotations

from typing import Any

from loguru import logger

from app.agent_kernel.memory.compaction import build_run_summary_payload
from app.agent_kernel.memory.server_cards import render_server_cards_prompt
from app.agent_kernel.runtime.context import build_ops_prompt_context
from servers.agents.multi_agent_engine_config import MAX_TASK_ITERATIONS


async def build_multi_agent_ops_prompt_context(engine: Any) -> str:
    """Load memory-backed context for multi-agent prompts."""
    cards = []
    server_ids: list[int] = []
    group_ids: list[int] = []
    for server in engine.servers[:3]:
        server_ids.append(server.id)
        if getattr(server, "group_id", None):
            group_ids.append(server.group_id)
        try:
            cards.append(await engine.memory_store.get_server_card(server.id))
        except Exception as exc:
            logger.debug("Failed to load memory card for server {}: {}", getattr(server, "id", "?"), exc)
    server_memory_prompt = render_server_cards_prompt(cards, max_cards=3, max_records=6)
    engine.server_memory_prompt = server_memory_prompt
    recipes_query = "\n".join(
        part for part in [engine.agent.goal or engine.agent.ai_prompt or "", *engine.role_spec.focus_areas] if part
    )
    engine.operational_recipes_prompt = await engine.memory_store.build_operational_recipes_prompt(
        recipes_query,
        server_ids=server_ids,
        group_ids=list(dict.fromkeys(group_ids)),
        limit=5,
    )
    tool_registry_prompt = engine.tool_registry.build_prompt_slice(limit=10) if engine.tool_registry else ""
    return build_ops_prompt_context(
        role_spec=engine.role_spec,
        permission_mode=engine.permission_engine.mode,
        server_memory_prompt=server_memory_prompt,
        operational_recipes_prompt=engine.operational_recipes_prompt,
        tool_registry_prompt=tool_registry_prompt,
        max_iterations=MAX_TASK_ITERATIONS,
        session_timeout=engine.session_timeout,
    )


async def persist_multi_agent_ops_summary(
    engine: Any,
    *,
    run,
    final_status: str,
    final_report: str,
    plan_tasks: list[dict],
) -> None:
    """Persist compact multi-agent run memory."""
    if not getattr(run, "pk", None):
        return
    flat_iterations = []
    for task in plan_tasks:
        for item in task.get("iterations", [])[-2:]:
            flat_iterations.append(item)
    tool_calls = [
        {"tool": item.get("action"), "result": item.get("observation", "")}
        for item in flat_iterations
        if item.get("action")
    ]
    payload = build_run_summary_payload(
        run=run,
        role_slug=engine.role_spec.slug,
        final_status=final_status,
        final_report=final_report,
        iterations=flat_iterations,
        tool_calls=tool_calls,
        verification_summary=engine.permission_engine.verification_summary(),
    )
    await engine.memory_store.append_run_summary(run.pk, payload)
