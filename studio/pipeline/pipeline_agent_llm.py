from __future__ import annotations

import contextlib
import logging
import time
from typing import Any

from asgiref.sync import sync_to_async as _s2a

from app.agent_kernel.memory.compaction import compact_text
from app.agent_kernel.memory.server_cards import render_server_cards_prompt
from app.core.model_utils import resolve_provider_and_model
from app.pipeline_memory_provider import build_pipeline_operational_recipes, get_pipeline_server_card
from studio.models import PipelineRun
from studio.services import get_owned_servers_by_ids

from .pipeline_context import (
    build_pipeline_ops_context,
    compact_node_outputs_context,
    pipeline_permission_mode,
    pipeline_role_slug,
    render_template_value,
)

logger = logging.getLogger(__name__)


def _s2a_fn(func, thread_sensitive=False):
    return _s2a(func, thread_sensitive=thread_sensitive)


def _resolve_llm_provider_and_model(config: dict) -> tuple[str, str]:
    provider, model = resolve_provider_and_model(
        config.get("provider"),
        config.get("model"),
        default_provider="auto",
    )
    # Empty model is valid: LLMProvider/model_manager pick purpose defaults.
    return provider, model or ""


async def _load_owned_servers(owner, server_ids: list[int]):
    if not server_ids:
        return []
    return await _s2a_fn(get_owned_servers_by_ids)(owner, server_ids, order_by="-updated_at")


def _server_ids_from_config(config: dict[str, Any], context: dict[str, Any]) -> list[int]:
    raw_server_ids = config.get("server_ids") or []
    if config.get("server_id") and not raw_server_ids:
        raw_server_ids = [config.get("server_id")]

    server_ids: list[int] = []
    for value in raw_server_ids[:3]:
        try:
            server_ids.append(int(value))
        except (TypeError, ValueError):
            continue
    if not server_ids and context.get("target_server_id"):
        with contextlib.suppress(TypeError, ValueError):
            server_ids.append(int(context.get("target_server_id")))
    return server_ids


async def _load_pipeline_server_memory(owner, config: dict[str, Any], context: dict[str, Any]) -> str:
    server_ids = _server_ids_from_config(config, context)
    if not server_ids:
        return "Память по серверам для этого pipeline node не выбрана."

    cards = []
    servers = await _load_owned_servers(owner, server_ids)
    for server in servers[:3]:
        try:
            cards.append(await get_pipeline_server_card(server.id))
        except Exception as exc:
            logger.debug("Failed to load pipeline server memory for %s: %s", server.id, exc)
    return render_server_cards_prompt(cards, max_cards=3, max_records=5)


async def _load_pipeline_operational_recipes(
    owner,
    config: dict[str, Any],
    context: dict[str, Any],
    *,
    role_slug: str,
    query: str,
) -> str:
    server_ids = _server_ids_from_config(config, context)

    group_ids: list[int] = []
    if server_ids:
        for server in await _load_owned_servers(owner, server_ids):
            if getattr(server, "group_id", None):
                group_ids.append(server.group_id)

    recipe_query = "\n".join(part for part in [query, role_slug] if part).strip()
    return await build_pipeline_operational_recipes(
        recipe_query,
        server_ids=server_ids,
        group_ids=list(dict.fromkeys(group_ids)),
        limit=4,
    )


async def execute_agent_llm_query(node: dict, context: dict, node_outputs: dict[str, dict], run: PipelineRun) -> dict:
    """
    Direct LLM query — no SSH needed.
    Sends a prompt (with all previous node outputs as context) to the chosen provider and returns the response.
    """
    config = node.get("data", {})
    prompt_template = config.get("prompt", "")
    system_prompt = config.get("system_prompt", "You are a helpful DevOps assistant.")
    include_all_outputs = config.get("include_all_outputs", True)
    purpose = str(config.get("purpose") or "opssummary").strip() or "opssummary"
    permission_mode = pipeline_permission_mode(config)
    role_slug = pipeline_role_slug(config)
    max_context_nodes = max(1, min(int(config.get("max_context_nodes", 6) or 6), 12))
    max_output_context_chars = max(200, min(int(config.get("max_output_chars", 1200) or 1200), 4000))
    provider, specific_model = _resolve_llm_provider_and_model(config)

    if not prompt_template:
        return {"status": "failed", "error": "No prompt configured for llm_query node"}

    outputs_context = (
        compact_node_outputs_context(node_outputs, max_nodes=max_context_nodes, max_chars=max_output_context_chars)
        if include_all_outputs
        else ""
    )

    substitutions = dict(context)
    substitutions["all_outputs"] = outputs_context
    prompt = render_template_value(prompt_template, substitutions)

    owner, actor = await _s2a_fn(lambda: (run.pipeline.owner, run.triggered_by or run.pipeline.owner))()
    from core_ui.ai_model_policy import user_can_manage_ai_routing

    if not await _s2a_fn(user_can_manage_ai_routing)(actor):
        config = {**config, "provider": "auto", "model": "", "provider_binding": {}}
        provider, specific_model = "auto", None
    server_memory_prompt = await _load_pipeline_server_memory(owner, config, context)
    operational_recipes_prompt = await _load_pipeline_operational_recipes(
        owner,
        config,
        context,
        role_slug=role_slug,
        query=prompt,
    )
    ops_context = build_pipeline_ops_context(
        role_slug=role_slug,
        permission_mode=permission_mode,
        server_memory_prompt=server_memory_prompt,
        operational_recipes_prompt=operational_recipes_prompt,
        tool_spec_lines="- llm_query: reasoning / summarization / planning [general / read]",
        max_iterations=1,
    )

    full_prompt = f"{system_prompt}\n\n{prompt}" if system_prompt else prompt
    if outputs_context and "{all_outputs}" not in prompt_template and include_all_outputs:
        full_prompt = f"{system_prompt}\n\n{ops_context}\n\n## Context from previous pipeline steps:\n{outputs_context}\n\n## Your task:\n{prompt}"
    else:
        full_prompt = f"{system_prompt}\n\n{ops_context}\n\n{prompt}" if system_prompt else f"{ops_context}\n\n{prompt}"

    try:
        from app.core.llm import LLMProvider
        from studio.services.ai_execution_context import build_pipeline_execution_context

        t0 = time.time()
        llm = LLMProvider()
        execution_context = await build_pipeline_execution_context(
            run,
            purpose=purpose,
            node_id=str(node.get("id") or "llm_query"),
            config=config,
        )
        output_chunks: list[str] = []
        async for chunk in llm.stream_chat(
            full_prompt,
            model=provider,
            specific_model=specific_model or None,
            purpose=purpose,
            execution_context=execution_context,
        ):
            output_chunks.append(chunk)
        output_text = compact_text("".join(output_chunks), limit=6000)
        elapsed = int((time.time() - t0) * 1000)
        logger.info(
            "llm_query node %s: %s/%s %.1fs, %d chars",
            node.get("id"),
            provider,
            specific_model,
            elapsed / 1000,
            len(output_text),
        )

        if output_text.strip().startswith("Error:"):
            return {"status": "failed", "error": output_text.strip(), "output": output_text}
        return {"status": "completed", "output": output_text}
    except Exception as exc:
        logger.exception("llm_query node %s failed", node.get("id"))
        return {"status": "failed", "error": str(exc)}
