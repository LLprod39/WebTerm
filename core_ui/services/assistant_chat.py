from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass
from typing import Any

from django.db import transaction
from django.utils import timezone
from loguru import logger

from app.assistant_actions import AssistantActionContext, AssistantActionError, get_action_spec, list_action_specs
from app.core.llm import LLMProvider
from app.egress_redaction import payload_preview, redact_egress_payload
from core_ui.access import feature_allowed_for_user
from core_ui.activity import log_user_activity
from core_ui.models import AssistantAction, ChatMessage, ChatSession, UserActivityLog

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


@dataclass
class AssistantTurnResult:
    user_message: ChatMessage
    assistant_message: ChatMessage
    actions: list[AssistantAction]


def serialize_action(action: AssistantAction) -> dict[str, Any]:
    return {
        "id": action.pk,
        "chat_id": action.session_id,
        "message_id": action.message_id,
        "action_type": action.action_type,
        "title": action.title,
        "description": action.description,
        "status": action.status,
        "risk": action.risk,
        "required_feature": action.required_feature,
        "requires_confirmation": action.requires_confirmation,
        "input": action.safe_preview,
        "result": action.result_payload,
        "error": action.error,
        "target_url": action.target_url,
        "created_at": action.created_at.isoformat(),
        "updated_at": action.updated_at.isoformat(),
        "confirmed_at": action.confirmed_at.isoformat() if action.confirmed_at else None,
        "completed_at": action.completed_at.isoformat() if action.completed_at else None,
    }


def serialize_message(message: ChatMessage) -> dict[str, Any]:
    actions = [serialize_action(action) for action in message.actions.order_by("created_at", "id")]
    metadata = dict(message.metadata or {})
    if actions:
        metadata["actions"] = actions
    return {
        "id": message.pk,
        "role": message.role,
        "content": message.content,
        "metadata": metadata,
        "created_at": message.created_at.isoformat(),
    }


def serialize_chat_session(session: ChatSession, *, include_messages: bool = False) -> dict[str, Any]:
    payload = {
        "id": session.pk,
        "title": session.title,
        "created_at": session.created_at.isoformat(),
        "updated_at": session.updated_at.isoformat(),
    }
    if include_messages:
        payload["messages"] = [serialize_message(message) for message in session.messages.order_by("created_at", "id")]
    return payload


def list_chat_sessions(user) -> list[dict[str, Any]]:
    sessions = ChatSession.objects.filter(user=user).order_by("-updated_at")[:50]
    return [serialize_chat_session(session) for session in sessions]


def get_chat_session(user, chat_id: int) -> ChatSession | None:
    return ChatSession.objects.filter(user=user, pk=chat_id).first()


def create_chat_session(user, *, title: str = "") -> ChatSession:
    return ChatSession.objects.create(user=user, title=(title or "Новый чат").strip()[:200] or "Новый чат")


def _redacted_preview(payload: dict[str, Any]) -> dict[str, Any]:
    redacted, _report, _hashes = redact_egress_payload(payload or {})
    if isinstance(redacted, dict):
        return redacted
    return {"preview": payload_preview(redacted)}


def _chat_history(session: ChatSession) -> list[dict[str, str]]:
    rows = session.messages.order_by("-created_at", "-id")[:10]
    return [
        {"role": row.role, "content": row.content[:4000]}
        for row in reversed(list(rows))
        if row.role in {ChatMessage.ROLE_USER, ChatMessage.ROLE_ASSISTANT}
    ]


def _action_catalog_for_user(user) -> list[dict[str, Any]]:
    catalog = []
    for spec in list_action_specs():
        if feature_allowed_for_user(user, spec.required_feature):
            catalog.append(spec.to_prompt_dict())
    return catalog


def _runtime_context_for_user(user) -> dict[str, Any]:
    context: dict[str, Any] = {
        "agents": [],
        "servers": [],
        "pipelines": [],
        "selection_rules": [
            "Use ids from this snapshot when the name match is exact or unique.",
            "Ask a clarification when several objects match the same operator phrase.",
            "Never infer secrets or credentials from names.",
        ],
    }

    if feature_allowed_for_user(user, "agents"):
        try:
            from app.runtime_limits import ACTIVE_AGENT_RUN_STATUSES
            from servers.models import AgentRun, ServerAgent

            agents = list(ServerAgent.objects.filter(user=user).prefetch_related("servers").order_by("-updated_at", "-id")[:30])
            active_runs = {}
            for run in (
                AgentRun.objects.filter(agent__in=agents, status__in=ACTIVE_AGENT_RUN_STATUSES)
                .order_by("agent_id", "-started_at", "-id")
            ):
                active_runs.setdefault(run.agent_id, run)
            context["agents"] = [
                {
                    "id": agent.id,
                    "name": agent.name,
                    "mode": agent.mode,
                    "agent_type": agent.agent_type,
                    "goal": (agent.goal or agent.ai_prompt or "")[:500],
                    "server_ids": list(agent.servers.values_list("id", flat=True)[:8]),
                    "server_names": list(agent.servers.values_list("name", flat=True)[:8]),
                    "is_enabled": bool(agent.is_enabled),
                    "active_run_id": active_runs[agent.id].id if agent.id in active_runs else None,
                    "active_run_status": active_runs[agent.id].status if agent.id in active_runs else "",
                }
                for agent in agents
            ]
        except Exception as exc:  # noqa: BLE001 - context is best-effort.
            logger.debug("assistant chat agent context skipped: {}", exc)

    if feature_allowed_for_user(user, "servers"):
        try:
            from servers.views.server_helpers import _accessible_servers_queryset

            servers = list(_accessible_servers_queryset(user).order_by("-updated_at", "-id")[:30])
            context["servers"] = [
                {
                    "id": server.id,
                    "name": server.name,
                    "host": server.host,
                    "username": server.username,
                    "server_type": server.server_type,
                    "is_active": bool(server.is_active),
                    "detected_os": server.detected_os,
                }
                for server in servers
            ]
        except Exception as exc:  # noqa: BLE001 - context is best-effort.
            logger.debug("assistant chat server context skipped: {}", exc)

    if feature_allowed_for_user(user, "studio_pipelines"):
        try:
            from studio.views.pipeline_helpers import _pipeline_queryset_for_user

            pipelines = list(_pipeline_queryset_for_user(user).order_by("-updated_at", "-id")[:25])
            context["pipelines"] = [
                {
                    "id": pipeline.id,
                    "name": pipeline.name,
                    "description": (pipeline.description or "")[:400],
                    "node_count": len(pipeline.nodes or []),
                    "tag_count": len(pipeline.tags or []),
                    "is_template": bool(pipeline.is_template),
                }
                for pipeline in pipelines
            ]
        except Exception as exc:  # noqa: BLE001 - context is best-effort.
            logger.debug("assistant chat pipeline context skipped: {}", exc)

    return context


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


def _create_action(
    *,
    user,
    session: ChatSession,
    message: ChatMessage,
    proposal: dict[str, Any],
) -> AssistantAction | None:
    spec = get_action_spec(proposal["action_type"])
    if spec is None:
        return None
    if not feature_allowed_for_user(user, spec.required_feature):
        return AssistantAction.objects.create(
            user=user,
            session=session,
            message=message,
            action_type=spec.action_type,
            title=proposal.get("title") or spec.label,
            description=proposal.get("description") or spec.description,
            status=AssistantAction.STATUS_FAILED,
            risk=spec.risk,
            required_feature=spec.required_feature,
            requires_confirmation=spec.requires_confirmation,
            input_payload=proposal.get("input") or {},
            safe_preview=_redacted_preview(proposal.get("input") or {}),
            error=f"Feature access required: {spec.required_feature}",
            completed_at=timezone.now(),
        )

    status = AssistantAction.STATUS_REQUIRES_CONFIRMATION if spec.requires_confirmation else AssistantAction.STATUS_PROPOSED
    return AssistantAction.objects.create(
        user=user,
        session=session,
        message=message,
        action_type=spec.action_type,
        title=proposal.get("title") or spec.label,
        description=proposal.get("description") or spec.description,
        status=status,
        risk=spec.risk,
        required_feature=spec.required_feature,
        requires_confirmation=spec.requires_confirmation,
        input_payload=proposal.get("input") or {},
        safe_preview=_redacted_preview(proposal.get("input") or {}),
    )


def execute_action(action: AssistantAction, *, request=None, confirmed: bool = False) -> AssistantAction:
    spec = get_action_spec(action.action_type)
    if spec is None or spec.handler is None:
        action.status = AssistantAction.STATUS_FAILED
        action.error = f"Unknown assistant action: {action.action_type}"
        action.completed_at = timezone.now()
        action.save(update_fields=["status", "error", "completed_at", "updated_at"])
        return action

    if not feature_allowed_for_user(action.user, spec.required_feature):
        action.status = AssistantAction.STATUS_FAILED
        action.error = f"Feature access required: {spec.required_feature}"
        action.completed_at = timezone.now()
        action.save(update_fields=["status", "error", "completed_at", "updated_at"])
        return action

    if action.requires_confirmation and not confirmed:
        action.status = AssistantAction.STATUS_REQUIRES_CONFIRMATION
        action.save(update_fields=["status", "updated_at"])
        return action

    action.status = AssistantAction.STATUS_RUNNING
    if confirmed:
        action.confirmed_at = timezone.now()
    action.save(update_fields=["status", "confirmed_at", "updated_at"])

    try:
        result = spec.handler(
            AssistantActionContext(
                user=action.user,
                input_payload=dict(action.input_payload or {}),
                request=request,
            )
        )
    except AssistantActionError as exc:
        action.status = AssistantAction.STATUS_FAILED
        action.error = exc.message
        action.result_payload = exc.details
    except Exception as exc:  # noqa: BLE001 - action failures must be persisted for the UI.
        action.status = AssistantAction.STATUS_FAILED
        action.error = str(exc) or "Assistant action failed"
        action.result_payload = {}
    else:
        action.status = AssistantAction.STATUS_COMPLETED
        action.error = ""
        action.result_payload = result if isinstance(result, dict) else {"result": result}
        target_url = str(action.result_payload.get("target_url") or "")
        if target_url:
            action.target_url = target_url[:300]
    action.completed_at = timezone.now()
    action.save(update_fields=["status", "error", "result_payload", "target_url", "completed_at", "updated_at"])
    return action


def cancel_action(action: AssistantAction) -> AssistantAction:
    if action.status in {
        AssistantAction.STATUS_COMPLETED,
        AssistantAction.STATUS_FAILED,
        AssistantAction.STATUS_CANCELLED,
        AssistantAction.STATUS_RUNNING,
    }:
        return action
    action.status = AssistantAction.STATUS_CANCELLED
    action.completed_at = timezone.now()
    action.save(update_fields=["status", "completed_at", "updated_at"])
    return action


def handle_user_message(session: ChatSession, user, message: str, *, request=None) -> AssistantTurnResult:
    text = str(message or "").strip()
    if not text:
        raise AssistantActionError("message is required")

    with transaction.atomic():
        user_message = ChatMessage.objects.create(session=session, role=ChatMessage.ROLE_USER, content=text)
        session.title = (session.title if session.messages.count() > 1 else text[:80]) or session.title
        session.save(update_fields=["title", "updated_at"])

    try:
        history = _chat_history(session)
        catalog = _action_catalog_for_user(user)
        runtime_context = _runtime_context_for_user(user)
        plan = asyncio.run(_call_planner(history=history, catalog=catalog, runtime_context=runtime_context, message=text))
    except Exception as exc:
        logger.exception("assistant chat planner failed; using heuristic fallback: {}", exc)
        runtime_context = _runtime_context_for_user(user)
        plan = _heuristic_plan(text)

    reply, proposals = _normalise_action_proposals(plan, text)
    reply, proposals = _contextualise_action_proposals(
        reply=reply,
        proposals=proposals,
        message=text,
        runtime_context=runtime_context,
    )
    assistant_message = ChatMessage.objects.create(
        session=session,
        role=ChatMessage.ROLE_ASSISTANT,
        content=reply,
        metadata={"source": "assistant_chat"},
    )

    actions: list[AssistantAction] = []
    for proposal in proposals:
        action = _create_action(user=user, session=session, message=assistant_message, proposal=proposal)
        if action is None:
            continue
        if not action.requires_confirmation and action.status == AssistantAction.STATUS_PROPOSED:
            action = execute_action(action, request=request, confirmed=False)
        actions.append(action)

    assistant_message.metadata = {
        **(assistant_message.metadata or {}),
        "action_ids": [action.pk for action in actions],
    }
    assistant_message.save(update_fields=["metadata"])

    log_user_activity(
        user=user,
        request=request,
        category="assistant",
        action="chat_message",
        status=UserActivityLog.STATUS_SUCCESS,
        description=text[:400],
        entity_type="chat_session",
        entity_id=str(session.pk),
        metadata={"actions": [action.action_type for action in actions]},
    )
    return AssistantTurnResult(user_message=user_message, assistant_message=assistant_message, actions=actions)
