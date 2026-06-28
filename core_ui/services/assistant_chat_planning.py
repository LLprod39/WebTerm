from __future__ import annotations

import json
import re
from typing import Any

from app.core.llm import LLMProvider

ASSISTANT_SYSTEM_PROMPT = """You are WebTermAI Chat, an operations assistant inside the WebTrerm platform.

You can answer normally and may propose structured actions. You cannot invent tools.
Only propose actions from the supplied action_catalog. Do not execute anything yourself.

Planning rules:
- Use runtime_context to resolve exact or unique object names into ids before proposing actions.
- If the operator asks to run/start/stop/reply/approve and runtime_context contains a unique matching object, propose the matching mutating action with that id.
- If a required id cannot be resolved uniquely, ask one short clarification and optionally propose a read-only list action.
- Do not answer with only a list action when the operator already named a concrete object and intent.
- Prefer one high-confidence action over several generic read actions.

Safety rules:
- Read-only actions may be executed automatically by the platform.
- Internal writes, runtime actions, external sends, mutations, and dangerous actions require operator confirmation.
- If required ids are missing, ask a concise question instead of guessing.
- Never include secrets in replies or action input.

Return only JSON:
{
  "reply": "short practical assistant message",
  "actions": [
    {
      "action_type": "registered.action.id",
      "title": "short action card title",
      "description": "what will happen",
      "input": {}
    }
  ]
}
"""


def _extract_json_object(raw: str) -> dict[str, Any] | None:
    text = str(raw or "").strip()
    if not text:
        return None
    text = re.sub(r"^```(?:json)?\s*", "", text).strip()
    text = re.sub(r"\s*```$", "", text).strip()
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        pass
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end <= start:
        return None
    try:
        parsed = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _first_int(text: str) -> int | None:
    match = re.search(r"\b(\d{1,10})\b", text)
    if not match:
        return None
    try:
        return int(match.group(1))
    except ValueError:
        return None


def _lookup_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().casefold())


def _looks_like_agent_run_request(message: str) -> bool:
    lower = _lookup_text(message)
    run_words = (
        "запусти",
        "запустить",
        "запускай",
        "старт",
        "стартуй",
        "start",
        "run",
        "launch",
        "execute",
    )
    return any(word in lower for word in run_words)


def _resolve_agent_from_context(
    runtime_context: dict[str, Any],
    *,
    message: str,
    input_payload: dict[str, Any],
) -> dict[str, Any] | None:
    agents = runtime_context.get("agents")
    if not isinstance(agents, list):
        return None
    agent_items = [agent for agent in agents if isinstance(agent, dict) and agent.get("id") and agent.get("name")]
    if not agent_items:
        return None

    explicit_sources = [
        input_payload.get("agent_name"),
        input_payload.get("name"),
        input_payload.get("agent"),
        input_payload.get("target"),
    ]
    message_text = _lookup_text(message)
    sources = [_lookup_text(source) for source in explicit_sources if _lookup_text(source)]
    sources.append(message_text)

    for source in sources:
        exact = [agent for agent in agent_items if _lookup_text(agent.get("name")) == source]
        if len(exact) == 1:
            return exact[0]

    scored: list[tuple[int, dict[str, Any]]] = []
    for agent in agent_items:
        name = _lookup_text(agent.get("name"))
        if not name:
            continue
        if any(name in source for source in sources):
            scored.append((len(name), agent))

    if scored:
        scored.sort(key=lambda item: item[0], reverse=True)
        best_length = scored[0][0]
        best = [agent for length, agent in scored if length == best_length]
        if len(best) == 1:
            return best[0]

    if len(agent_items) == 1 and any(word in message_text for word in ("агент", "agent")):
        return agent_items[0]

    return None


def _heuristic_plan(message: str) -> dict[str, Any]:
    text = str(message or "").strip()
    lower = text.lower()
    actions: list[dict[str, Any]] = []
    reply = "Понял. Могу подготовить действие и показать его перед выполнением."

    pipeline_words = ("pipeline", "пайплайн", "пайплаин", "воркфлоу", "workflow")
    create_words = ("созда", "состав", "собер", "постро", "сдела", "create", "build", "draft")
    if any(word in lower for word in pipeline_words) and any(word in lower for word in create_words):
        actions.append(
            {
                "action_type": "studio.pipeline_draft.create",
                "title": "Собрать черновик пайплайна",
                "description": "Создать Studio draft из сообщения и пройти встроенную validation/risk проверку.",
                "input": {
                    "pipeline_name": text[:80] or "AI Chat Pipeline",
                    "user_message": text,
                    "compiler_mode": "",
                },
            }
        )
        reply = "Подготовлю черновик пайплайна через Studio Drafts. После подтверждения он появится как draft, без запуска runtime-действий."
    elif any(word in lower for word in pipeline_words) and any(word in lower for word in ("спис", "покажи", "list", "show")):
        actions.append(
            {
                "action_type": "studio.pipelines.list",
                "title": "Показать пайплайны",
                "description": "Получить доступные Studio pipelines.",
                "input": {"q": ""},
            }
        )
        reply = "Покажу доступные пайплайны."

    if not actions and any(word in lower for word in ("возможн", "capabil", "умеешь", "can you")):
        actions.append(
            {
                "action_type": "studio.capabilities.registry",
                "title": "Показать возможности Studio",
                "description": "Получить registry доступных node families, MCP servers и skills.",
                "input": {},
            }
        )
        reply = "Покажу доступные возможности Studio и связанные ресурсы."

    if not actions and "mcp" in lower and any(word in lower for word in ("спис", "покажи", "list", "show")):
        actions.append(
            {
                "action_type": "studio.mcp.list",
                "title": "Показать MCP servers",
                "description": "Получить доступные Studio MCP servers без запуска tools.",
                "input": {},
            }
        )
        reply = "Покажу доступные MCP servers."

    if not actions and any(word in lower for word in ("скилл", "skill")) and any(
        word in lower for word in ("спис", "покажи", "list", "show")
    ):
        actions.append(
            {
                "action_type": "studio.skills.list",
                "title": "Показать Studio skills",
                "description": "Получить доступный каталог Studio skills.",
                "input": {},
            }
        )
        reply = "Покажу доступные Studio skills."

    if not actions and any(word in lower for word in ("скилл", "skill")) and any(
        word in lower for word in ("валид", "проверь", "validate", "check")
    ):
        actions.append(
            {
                "action_type": "studio.skills.validate",
                "title": "Проверить Studio skills",
                "description": "Запустить read-only validation доступных Studio skills.",
                "input": {"slugs": []},
            }
        )
        reply = "Проверю доступные Studio skills."

    if not actions and "агент" in lower and any(word in lower for word in ("спис", "покажи", "list", "show")):
        actions.append(
            {
                "action_type": "agents.list",
                "title": "Показать агентов",
                "description": "Получить список доступных агентов и runtime overview.",
                "input": {},
            }
        )
        reply = "Покажу доступных агентов."

    if not actions and "агент" in lower and any(word in lower for word in ("запусти", "start", "run")):
        agent_id = _first_int(lower)
        if agent_id:
            actions.append(
                {
                    "action_type": "agent.run",
                    "title": f"Запустить агента #{agent_id}",
                    "description": "Запустить существующего агента через текущий agent runtime.",
                    "input": {"agent_id": agent_id},
                }
            )
            reply = "Подготовил запуск агента. Перед стартом нужно подтверждение."

    if not actions and "сервер" in lower and any(word in lower for word in ("диагност", "overview", "снимок", "snapshot")):
        server_id = _first_int(lower)
        if server_id:
            actions.append(
                {
                    "action_type": "server.diagnostics.overview",
                    "title": f"Снять обзор сервера #{server_id}",
                    "description": "Получить read-only Linux overview через существующий Servers UI runtime.",
                    "input": {"server_id": server_id},
                }
            )
            reply = "Сниму read-only overview сервера."

    return {"reply": reply, "actions": actions, "_planned_by": "heuristic"}


async def _call_planner(
    *,
    history: list[dict[str, str]],
    catalog: list[dict[str, Any]],
    runtime_context: dict[str, Any],
    message: str,
) -> dict[str, Any]:
    if not catalog:
        return {"reply": "У вас нет доступных assistant actions. Могу ответить текстом.", "actions": [], "_planned_by": "system"}
    prompt = json.dumps(
        {
            "message": message,
            "history": history,
            "action_catalog": catalog,
            "runtime_context": runtime_context,
        },
        ensure_ascii=False,
    )
    provider = LLMProvider()
    chunks: list[str] = []
    async for chunk in provider.stream_chat(
        prompt,
        model="auto",
        purpose="orchestrator",
        system_prompt=ASSISTANT_SYSTEM_PROMPT,
        json_mode=True,
    ):
        chunks.append(chunk)
    parsed = _extract_json_object("".join(chunks))
    if not parsed:
        return {"reply": "".join(chunks).strip() or "Готов помочь. Уточните действие.", "actions": [], "_planned_by": "llm"}
    parsed["_planned_by"] = "llm"
    return parsed


def _normalise_action_proposals(plan: dict[str, Any], fallback_message: str) -> tuple[str, list[dict[str, Any]]]:
    reply = str(plan.get("reply") or "").strip() or "Готов помочь."
    raw_actions = plan.get("actions")
    if not isinstance(raw_actions, list):
        raw_actions = []
    proposals = []
    for item in raw_actions[:5]:
        if not isinstance(item, dict):
            continue
        action_type = str(item.get("action_type") or "").strip()
        if not action_type:
            continue
        input_payload = item.get("input") if isinstance(item.get("input"), dict) else {}
        proposals.append(
            {
                "action_type": action_type,
                "title": str(item.get("title") or "").strip(),
                "description": str(item.get("description") or "").strip(),
                "input": input_payload,
            }
        )
    if not proposals and plan.get("_planned_by") != "llm":
        heuristic = _heuristic_plan(fallback_message)
        if heuristic.get("actions"):
            return str(heuristic.get("reply") or reply), list(heuristic.get("actions") or [])
    return reply, proposals


def _contextualise_action_proposals(
    *,
    reply: str,
    proposals: list[dict[str, Any]],
    message: str,
    runtime_context: dict[str, Any],
) -> tuple[str, list[dict[str, Any]]]:
    if not _looks_like_agent_run_request(message):
        return reply, proposals

    agent = _resolve_agent_from_context(runtime_context, message=message, input_payload={})
    if not agent:
        return reply, proposals

    agent_id = agent.get("id")
    agent_name = str(agent.get("name") or f"#{agent_id}").strip()
    next_proposals: list[dict[str, Any]] = []
    changed = False

    for proposal in proposals:
        action_type = proposal.get("action_type")
        input_payload = dict(proposal.get("input") or {})
        if action_type == "agent.run":
            if not input_payload.get("agent_id"):
                input_payload["agent_id"] = agent_id
                changed = True
            next_proposals.append(
                {
                    **proposal,
                    "title": proposal.get("title") or f"Запустить {agent_name}",
                    "description": proposal.get("description") or "Запустить найденного агента через текущий runtime.",
                    "input": input_payload,
                }
            )
            continue
        if action_type == "agents.list":
            changed = True
            continue
        next_proposals.append(proposal)

    has_agent_run = any(proposal.get("action_type") == "agent.run" for proposal in next_proposals)
    if not has_agent_run:
        next_proposals.insert(
            0,
            {
                "action_type": "agent.run",
                "title": f"Запустить {agent_name}",
                "description": "Запустить найденного агента через текущий runtime. Перед стартом требуется подтверждение.",
                "input": {"agent_id": agent_id},
            },
        )
        changed = True

    if changed:
        reply = f"Нашёл {agent_name} (#{agent_id}). Подготовил запуск; перед стартом нужно подтверждение."

    return reply, next_proposals[:5]
