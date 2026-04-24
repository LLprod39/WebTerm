from __future__ import annotations

import asyncio
import json
from typing import Any

from app.agent_kernel.memory.redaction import sanitize_prompt_context_text
from app.core.llm import LLMProvider


class PipelineAssistantError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.message = message
        self.status = status


_SYSTEM_PROMPT = """Ты — корпоративный AI copilot для Studio Pipeline Editor.

Ты помогаешь администратору проектировать, проверять и улучшать ВЕСЬ pipeline. Если передана focus node, ты можешь также дать точечный patch для неё.

Правила:
- Смотри на весь граф, а не только на одну ноду.
- Предлагай изменения с учетом реальных доступных ресурсов: servers, agent configs, MCP servers, skills.
- Если можно использовать существующий ресурс, ссылайся на него по точному ID.
- Если нужен точечный конфиг ноды, указывай target_node_id и заполняй node_patch только полями data этой ноды.
- Если пользователь хочет изменить несколько существующих шагов или убрать мусор из графа, используй graph_patch.update_nodes / remove_node_ids / remove_edge_ids.
- Если хочешь предложить новые шаги или ветку, используй graph_patch.nodes и graph_patch.edges.
- Если вопрос общий по pipeline, можешь оставить target_node_id пустым и дать только graph_patch и reply.
- Не удаляй существующие значения без явной просьбы пользователя.
- Для logic/condition обязательно учитывай source_node_id и входящие связи.
- Для agent/mcp_call предпочитай доступные MCP tools и валидные JSON arguments.
- reply должен быть коротким и практичным: что понял, что меняешь, что осталось проверить. Избегай длинных таблиц и воды.
- Если граф почти пустой или пользователь просит «собери пайплайн», верни готовый starter workflow, а не только советы.
- Возвращай только JSON-объект без markdown-обёрток, префиксов и пояснений вне JSON.

Верни ТОЛЬКО JSON-объект строго такого вида:
{
  "reply": "Markdown explanation for the operator",
  "target_node_id": null,
  "node_patch": {},
  "graph_patch": {
    "anchor_node_id": null,
    "nodes": [
      {
        "ref": "new_step_1",
        "type": "agent/llm_query",
        "label": "Optional human label",
        "data": {},
        "x_offset": 260,
        "y_offset": 0
      }
    ],
    "edges": [
      {
        "source": "existing_node_id_or_ref",
        "target": "existing_node_id_or_ref",
        "label": ""
      }
    ],
    "update_nodes": [
      {
        "node_id": "existing_node_id",
        "data": {}
      }
    ],
    "remove_node_ids": [],
    "remove_edge_ids": []
  },
  "warnings": ["optional warning"]
}

Правила для graph_patch:
- graph_patch.nodes / graph_patch.edges должны содержать только НОВЫЕ ноды и новые связи.
- В nodes[].ref используй короткие уникальные временные идентификаторы.
- В edges[].source / edges[].target можно ссылаться либо на существующий node_id, либо на ref из graph_patch.nodes.
- Для правки существующих нод используй graph_patch.update_nodes.
- Для удаления существующих элементов используй remove_node_ids и remove_edge_ids.
- Если нужны только текстовые рекомендации без вставки в graph, оставляй graph_patch пустым.
- Используй только допустимые типы нод:
  trigger/manual, trigger/webhook, trigger/schedule, trigger/monitoring,
  agent/react, agent/multi, agent/ssh_cmd, agent/llm_query, agent/mcp_call,
  logic/condition, logic/parallel, logic/merge, logic/wait, logic/human_approval, logic/telegram_input,
  output/report, output/webhook, output/email, output/telegram"""


def _extract_json_object(raw_text: str) -> dict[str, Any]:
    text = (raw_text or "").strip()
    if not text:
        return {}
    text = text.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return {}
    try:
        parsed = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _prompt_json(value: object, *, limit: int) -> str:
    try:
        serialized = json.dumps(value, ensure_ascii=False, indent=2)
    except TypeError:
        serialized = json.dumps(str(value), ensure_ascii=False)
    sanitized = sanitize_prompt_context_text(serialized).text.strip()
    return sanitized[:limit] if len(sanitized) > limit else sanitized


def _sanitize_graph_patch(raw_graph_patch: object, *, fallback_anchor: str | None = None) -> dict[str, Any]:
    if not isinstance(raw_graph_patch, dict):
        return {
            "anchor_node_id": fallback_anchor,
            "nodes": [],
            "edges": [],
            "update_nodes": [],
            "remove_node_ids": [],
            "remove_edge_ids": [],
        }

    raw_nodes = raw_graph_patch.get("nodes")
    raw_edges = raw_graph_patch.get("edges")
    if not isinstance(raw_nodes, list):
        raw_nodes = []
    if not isinstance(raw_edges, list):
        raw_edges = []

    nodes: list[dict[str, Any]] = []
    for item in raw_nodes[:24]:
        if not isinstance(item, dict):
            continue
        ref = str(item.get("ref") or "").strip()
        node_type = str(item.get("type") or "").strip()
        if not ref or not node_type:
            continue
        raw_data = item.get("data")
        data = raw_data if isinstance(raw_data, dict) else {}
        label = str(item.get("label") or "").strip()
        try:
            x_offset = float(item["x_offset"]) if item.get("x_offset") not in (None, "") else None
        except (TypeError, ValueError):
            x_offset = None
        try:
            y_offset = float(item["y_offset"]) if item.get("y_offset") not in (None, "") else None
        except (TypeError, ValueError):
            y_offset = None
        nodes.append(
            {
                "ref": ref,
                "type": node_type,
                "data": data,
                "label": label or None,
                "x_offset": x_offset,
                "y_offset": y_offset,
            }
        )

    edges: list[dict[str, Any]] = []
    for item in raw_edges[:48]:
        if not isinstance(item, dict):
            continue
        source = str(item.get("source") or "").strip()
        target = str(item.get("target") or "").strip()
        if not source or not target:
            continue
        edges.append(
            {
                "source": source,
                "target": target,
                "label": str(item.get("label") or "").strip() or None,
                "source_handle": str(item.get("source_handle") or "").strip() or None,
                "target_handle": str(item.get("target_handle") or "").strip() or None,
            }
        )

    raw_update_nodes = raw_graph_patch.get("update_nodes")
    if not isinstance(raw_update_nodes, list):
        raw_update_nodes = []
    update_nodes: list[dict[str, Any]] = []
    for item in raw_update_nodes[:24]:
        if not isinstance(item, dict):
            continue
        node_id = str(item.get("node_id") or "").strip()
        raw_data = item.get("data")
        if not node_id or not isinstance(raw_data, dict):
            continue
        update_nodes.append({"node_id": node_id, "data": raw_data})

    raw_remove_node_ids = raw_graph_patch.get("remove_node_ids")
    if not isinstance(raw_remove_node_ids, list):
        raw_remove_node_ids = []
    remove_node_ids = [str(item).strip() for item in raw_remove_node_ids[:24] if str(item).strip()]

    raw_remove_edge_ids = raw_graph_patch.get("remove_edge_ids")
    if not isinstance(raw_remove_edge_ids, list):
        raw_remove_edge_ids = []
    remove_edge_ids = [str(item).strip() for item in raw_remove_edge_ids[:48] if str(item).strip()]

    anchor_node_id = str(raw_graph_patch.get("anchor_node_id") or "").strip() or fallback_anchor
    return {
        "anchor_node_id": anchor_node_id,
        "nodes": nodes,
        "edges": edges,
        "update_nodes": update_nodes,
        "remove_node_ids": remove_node_ids,
        "remove_edge_ids": remove_edge_ids,
    }


async def _call_llm(*, user_prompt: str) -> str:
    provider = LLMProvider()
    chunks: list[str] = []
    async for chunk in provider.stream_chat(
        user_prompt,
        model="auto",
        purpose="chat",
        system_prompt=_SYSTEM_PROMPT,
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
) -> dict[str, Any]:
    return {
        "pipeline_name": pipeline_name,
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
    }


def build_pipeline_assistant_response(
    *,
    user_message: str,
    conversation_history: list[dict[str, Any]],
    assistant_context: dict[str, Any],
    known_node_ids: set[str] | None = None,
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
    if not parsed:
        fallback_reply = sanitize_prompt_context_text(raw_response).text.strip() or "Ассистент вернул невалидный JSON-ответ."
        return {
            "reply": fallback_reply,
            "target_node_id": None,
            "node_patch": {},
            "graph_patch": _sanitize_graph_patch(None),
            "warnings": ["Ассистент вернул невалидный structured output."],
        }

    reply = str(parsed.get("reply") or "").strip() or sanitize_prompt_context_text(raw_response).text.strip() or "No assistant response."
    target_node_id = str(parsed.get("target_node_id") or "").strip() or None
    node_patch = parsed.get("node_patch")
    if not isinstance(node_patch, dict):
        node_patch = {}

    warnings = parsed.get("warnings")
    if not isinstance(warnings, list):
        warnings = []
    warning_items = [str(item) for item in warnings if str(item).strip()][:8]

    known_ids = known_node_ids or set()
    if target_node_id and target_node_id not in known_ids:
        warning_items.append(f"Unknown target_node_id '{target_node_id}' ignored.")
        target_node_id = None
        node_patch = {}
    if not target_node_id:
        node_patch = {}

    return {
        "reply": reply,
        "target_node_id": target_node_id,
        "node_patch": node_patch,
        "graph_patch": _sanitize_graph_patch(parsed.get("graph_patch"), fallback_anchor=target_node_id),
        "warnings": warning_items[:8],
    }
