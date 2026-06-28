from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

from django.db import transaction
from django.utils import timezone
from loguru import logger

from app.assistant_actions import (
    AssistantActionContext,
    AssistantActionError,
    build_runtime_context,
    get_action_spec,
    list_action_specs,
)
from app.egress_redaction import payload_preview, redact_egress_payload
from core_ui.access import feature_allowed_for_user
from core_ui.activity import log_user_activity
from core_ui.models import AssistantAction, ChatMessage, ChatSession, UserActivityLog
from core_ui.services.assistant_chat_planning import (
    _call_planner,
    _contextualise_action_proposals,
    _heuristic_plan,
    _normalise_action_proposals,
)


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
        runtime_context = build_runtime_context(user)
        plan = asyncio.run(_call_planner(history=history, catalog=catalog, runtime_context=runtime_context, message=text))
    except Exception as exc:
        logger.exception("assistant chat planner failed; using heuristic fallback: {}", exc)
        runtime_context = build_runtime_context(user)
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
