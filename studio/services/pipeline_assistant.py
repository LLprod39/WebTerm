from __future__ import annotations

import asyncio
from typing import Any

from app.agent_kernel.memory.redaction import sanitize_prompt_context_text
from app.core.llm import LLMProvider
from studio.services.pipeline_assistant_catalog import (
    NODE_TYPE_ALIASES,
    NODE_TYPE_CATALOG,
    _node_catalog_payload,
)
from studio.services.pipeline_assistant_context import (
    _extract_json_object,
    _normalize_confidence,
    _normalize_node_explanations,
    _normalize_resource_plan,
    _prompt_json,
    _string_items,
)
from studio.services.pipeline_assistant_fallback import handle_unusable_llm_response
from studio.services.pipeline_assistant_graph_patch import _sanitize_graph_patch
from studio.services.pipeline_assistant_interview import augment_response_with_interview_questions
from studio.services.pipeline_assistant_prompt import SYSTEM_PROMPT

__all__ = [
    "NODE_TYPE_ALIASES",
    "NODE_TYPE_CATALOG",
    "PipelineAssistantError",
    "build_pipeline_assistant_response",
    "get_pipeline_assistant_context",
]


class PipelineAssistantError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.message = message
        self.status = status


async def _call_llm(*, user_prompt: str) -> str:
    provider = LLMProvider()
    chunks: list[str] = []
    async for chunk in provider.stream_chat(
        user_prompt,
        model="auto",
        purpose="chat",
        system_prompt=SYSTEM_PROMPT,
        json_mode=True,
    ):
        chunks.append(chunk)
    return "".join(chunks)


def get_pipeline_assistant_context(
    *,
    pipeline_name: str,
    graph_overview: dict[str, Any],
    focus_node: dict[str, Any] | None,
    incoming_nodes: list[dict[str, Any]],
    outgoing_nodes: list[dict[str, Any]],
    graph_nodes: list[dict[str, Any]],
    available_agents: list[dict[str, Any]],
    available_servers: list[dict[str, Any]],
    available_mcp_servers: list[dict[str, Any]],
    selected_mcp_tools: list[dict[str, Any]],
    available_skills: list[dict[str, Any]],
    selected_skill_details: list[dict[str, Any]],
    intent: str = "edit",
    last_validation_errors: list[str] | None = None,
    last_run_summary: dict[str, Any] | None = None,
    draft_mode: bool = True,
    capability_registry: dict[str, Any] | None = None,
    template_recommendations: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "pipeline_name": pipeline_name,
        "intent": intent,
        "draft_mode": draft_mode,
        "node_catalog": _node_catalog_payload(),
        "graph_overview": graph_overview,
        "focus_node": focus_node,
        "incoming_nodes": incoming_nodes,
        "outgoing_nodes": outgoing_nodes,
        "graph_nodes": graph_nodes,
        "available_agents": available_agents,
        "available_servers": available_servers,
        "available_mcp_servers": available_mcp_servers,
        "selected_mcp_tools": selected_mcp_tools,
        "available_skills": available_skills,
        "selected_skill_details": selected_skill_details,
        "capability_registry": capability_registry or {},
        "template_recommendations": template_recommendations or [],
        "last_validation_errors": last_validation_errors or [],
        "last_run_summary": last_run_summary or {},
    }


def build_pipeline_assistant_response(
    *,
    user_message: str,
    conversation_history: list[dict[str, Any]],
    assistant_context: dict[str, Any],
    known_node_ids: set[str] | None = None,
    known_node_types: dict[str, str] | None = None,
    known_edges: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    safe_user_message = (
        sanitize_prompt_context_text(user_message).text.strip()[:4000]
        or "Запрос пользователя был отфильтрован как небезопасный prompt-контент."
    )
    user_prompt = f"""История диалога:
{_prompt_json(conversation_history, limit=12000)}

Контекст пайплайна:
{_prompt_json(assistant_context, limit=36000)}

Вопрос пользователя:
{safe_user_message}
"""

    loop = asyncio.new_event_loop()
    try:
        raw_response = loop.run_until_complete(_call_llm(user_prompt=user_prompt))
    except Exception as exc:
        raise PipelineAssistantError(f"LLM error: {exc}", 500) from exc
    finally:
        loop.close()

    parsed = _extract_json_object(raw_response)
    fallback_response, fallback_error = handle_unusable_llm_response(
        raw_text=raw_response,
        parsed=parsed,
        user_message=safe_user_message,
        assistant_context=assistant_context,
        known_node_types=known_node_types,
    )
    if fallback_response is not None:
        fallback_response.setdefault(
            "template_recommendations", assistant_context.get("template_recommendations") or []
        )
        return augment_response_with_interview_questions(fallback_response)
    if fallback_error:
        raise PipelineAssistantError(fallback_error, 502)
    if not parsed:
        fallback_reply = (
            sanitize_prompt_context_text(raw_response).text.strip() or "Ассистент вернул невалидный JSON-ответ."
        )
        return augment_response_with_interview_questions(
            {
                "reply": fallback_reply,
                "requirements": [],
                "assumptions": [],
                "questions": [],
                "resource_plan": _normalize_resource_plan({}, assistant_context),
                "target_node_id": None,
                "node_patch": {},
                "graph_patch": _sanitize_graph_patch(None),
                "node_explanations": {},
                "confidence": None,
                "warnings": ["Ассистент вернул невалидный structured output."],
                "patch_summary": "",
                "suggested_next_actions": [],
                "template_recommendations": assistant_context.get("template_recommendations") or [],
            }
        )

    reply = (
        str(parsed.get("reply") or "").strip()
        or sanitize_prompt_context_text(raw_response).text.strip()
        or "No assistant response."
    )
    target_node_id = str(parsed.get("target_node_id") or "").strip() or None
    node_patch = parsed.get("node_patch")
    if not isinstance(node_patch, dict):
        node_patch = {}

    warnings = parsed.get("warnings")
    if not isinstance(warnings, list):
        warnings = []
    warning_items = [str(item) for item in warnings if str(item).strip()][:8]

    suggested_next_actions = parsed.get("suggested_next_actions")
    if not isinstance(suggested_next_actions, list):
        suggested_next_actions = []
    suggested_next_action_items = [str(item).strip() for item in suggested_next_actions if str(item).strip()][:8]

    known_ids = known_node_ids or set()
    if target_node_id and target_node_id not in known_ids:
        warning_items.append(f"Unknown target_node_id '{target_node_id}' ignored.")
        target_node_id = None
        node_patch = {}
    if not target_node_id:
        node_patch = {}

    graph_patch = _sanitize_graph_patch(
        parsed.get("graph_patch"),
        fallback_anchor=target_node_id,
        known_node_types=known_node_types,
        known_edges=known_edges,
        task_hint=safe_user_message,
        warnings=warning_items,
    )

    return augment_response_with_interview_questions(
        {
            "reply": reply,
            "requirements": _string_items(parsed.get("requirements"), limit=12),
            "assumptions": _string_items(parsed.get("assumptions"), limit=8),
            "questions": _string_items(parsed.get("questions"), limit=3),
            "resource_plan": _normalize_resource_plan(parsed.get("resource_plan"), assistant_context),
            "target_node_id": target_node_id,
            "node_patch": node_patch,
            "graph_patch": graph_patch,
            "node_explanations": _normalize_node_explanations(parsed.get("node_explanations")),
            "confidence": _normalize_confidence(parsed.get("confidence")),
            "warnings": warning_items[:8],
            "patch_summary": str(parsed.get("patch_summary") or "").strip(),
            "suggested_next_actions": suggested_next_action_items,
            "template_recommendations": assistant_context.get("template_recommendations") or [],
            "selected_template": parsed.get("selected_template")
            if isinstance(parsed.get("selected_template"), dict)
            else None,
        }
    )
