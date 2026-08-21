from __future__ import annotations

import asyncio
from dataclasses import dataclass, replace
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
from core_ui.models import AssistantAction, ChatMessage, ChatSession, ChatTurnState, UserActivityLog
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
        "blast_radius": action.blast_radius or {},
        "dry_run_preview": action.dry_run_preview or {},
        "undo_payload": action.undo_payload or {},
        "async_run_ref": action.async_run_ref or {},
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
        "kind": getattr(session, "kind", None) or "manual",
        "pinned_context": getattr(session, "pinned_context", None) or {},
        "total_usage": getattr(session, "total_usage", None) or {},
        "provider_binding": getattr(session, "provider_binding", None) or {},
        "created_at": session.created_at.isoformat(),
        "updated_at": session.updated_at.isoformat(),
    }
    if include_messages:
        payload["messages"] = [serialize_message(message) for message in session.messages.order_by("created_at", "id")]
        # Open / parked turn — client uses this to keep working after navigation away
        active = (
            ChatTurnState.objects.filter(
                session_id=session.pk,
                status__in={
                    ChatTurnState.STATUS_RUNNING,
                    ChatTurnState.STATUS_RESUMING,
                    ChatTurnState.STATUS_AWAITING_ASYNC,
                    ChatTurnState.STATUS_AWAITING_CONFIRM,
                },
            )
            .select_related("assistant_message", "user_message", "pending_action")
            .order_by("-id")
            .first()
        )
        if active:
            assistant = active.assistant_message
            payload["active_turn"] = {
                "turn_id": active.pk,
                "status": active.status,
                "iteration": active.iteration,
                "busy": active.status
                in {
                    ChatTurnState.STATUS_RUNNING,
                    ChatTurnState.STATUS_RESUMING,
                    ChatTurnState.STATUS_AWAITING_ASYNC,
                },
                "assistant_message_id": assistant.pk if assistant else None,
                "assistant_text": (assistant.content or "") if assistant else "",
                "pending_action_id": active.pending_action_id,
            }
        else:
            payload["active_turn"] = None
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

    status = (
        AssistantAction.STATUS_REQUIRES_CONFIRMATION if spec.requires_confirmation else AssistantAction.STATUS_PROPOSED
    )
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


def execute_action(
    action: AssistantAction,
    *,
    request=None,
    confirmed: bool = False,
    typed_confirm: str | None = None,
) -> AssistantAction:
    # Atomically claim the action before invoking a side-effecting handler.  A
    # second tab/worker that confirms the same id observes RUNNING/COMPLETED and
    # returns without executing it again.
    with transaction.atomic():
        action = (
            AssistantAction.objects.select_for_update(of=("self",))
            .select_related("user", "session", "message")
            .get(pk=action.pk)
        )
        spec = get_action_spec(action.action_type)
        if action.status in {
            AssistantAction.STATUS_RUNNING,
            AssistantAction.STATUS_COMPLETED,
            AssistantAction.STATUS_FAILED,
            AssistantAction.STATUS_CANCELLED,
        }:
            return action
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

        if spec.risk != AssistantAction.RISK_READ:
            from servers.agents.agent_pilot_policy import user_can_automate

            if not user_can_automate(action.user, request=request):
                action.status = AssistantAction.STATUS_FAILED
                action.error = "Mutating actions require the automation capability"
                action.completed_at = timezone.now()
                action.save(update_fields=["status", "error", "completed_at", "updated_at"])
                return action

        if action.requires_confirmation and not confirmed:
            action.status = AssistantAction.STATUS_REQUIRES_CONFIRMATION
            action.save(update_fields=["status", "updated_at"])
            return action

        if confirmed:
            from core_ui.services.operator_security import validate_typed_confirm

            typed_error = validate_typed_confirm(action, typed_confirm)
            if typed_error:
                action.status = AssistantAction.STATUS_REQUIRES_CONFIRMATION
                action.error = typed_error
                action.save(update_fields=["status", "error", "updated_at"])
                return action

        action.status = AssistantAction.STATUS_RUNNING
        if confirmed:
            action.confirmed_at = timezone.now()
            action.error = ""
        action.save(update_fields=["status", "confirmed_at", "error", "updated_at"])

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
        if isinstance(action.result_payload, dict):
            if action.result_payload.get("blast_radius"):
                action.blast_radius = action.result_payload.get("blast_radius") or {}
            if action.result_payload.get("dry_run_preview"):
                action.dry_run_preview = action.result_payload.get("dry_run_preview") or {}
            if action.result_payload.get("undo_payload"):
                action.undo_payload = action.result_payload.get("undo_payload") or {}
            if action.result_payload.get("async") or action.result_payload.get("async_kind"):
                from core_ui.services.operator_async import normalize_async_ref

                action.async_run_ref = {
                    **(action.async_run_ref or {}),
                    **normalize_async_ref(action.result_payload, action_type=action.action_type),
                }
    action.completed_at = timezone.now()
    action.save(
        update_fields=[
            "status",
            "error",
            "result_payload",
            "target_url",
            "blast_radius",
            "dry_run_preview",
            "undo_payload",
            "async_run_ref",
            "completed_at",
            "updated_at",
        ]
    )
    return action


def cancel_action(action: AssistantAction) -> AssistantAction:
    with transaction.atomic():
        action = AssistantAction.objects.select_for_update().get(pk=action.pk)
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


def handle_user_message(
    session: ChatSession,
    user,
    message: str,
    *,
    request=None,
    provider_binding: dict[str, Any] | None = None,
) -> AssistantTurnResult:
    """Handle a user message via the Operator tool-calling loop.

    On loop failure BEFORE anything was persisted the turn falls back to the
    legacy planner flow, so chat keeps working even when native tool-calling
    is unavailable (provider without tools, transport failure). Mid-turn LLM
    failures are handled inside the loop itself (visible error bubble).
    """
    text = str(message or "").strip()
    if not text:
        raise AssistantActionError("message is required")
    from core_ui.services.operator_rate_limit import check_turn_rate_limit

    rate_error = check_turn_rate_limit(session, message=text)
    if rate_error:
        raise AssistantActionError(rate_error, status=429)

    last_message_id = session.messages.order_by("-id").values_list("id", flat=True).first() or 0

    # Preferred path: native tool-calling operator loop
    try:
        from core_ui.services.operator_loop import handle_operator_message_sync

        result = handle_operator_message_sync(
            session,
            user,
            text,
            request=request,
            provider_binding=provider_binding,
        )
        return AssistantTurnResult(
            user_message=result.user_message,
            assistant_message=result.assistant_message,
            actions=list(result.actions or []),
        )
    except ValueError as exc:
        # start_operator_turn guards raise before any messages are written
        logger.warning("operator loop rejected message: {}", exc)
        return _operator_error_turn(session, user, text, str(exc), request=request)
    except Exception as exc:
        turn_wrote_rows = (session.messages.order_by("-id").values_list("id", flat=True).first() or 0) > last_message_id
        if turn_wrote_rows:
            # Partial turn already visible in the chat — never duplicate rows.
            logger.exception("operator loop failed mid-turn: {}", exc)
            raise AssistantActionError(f"Оператор не смог ответить: {exc}") from exc
        logger.exception("operator loop failed before writes; planner fallback: {}", exc)
        return _planner_fallback_turn(
            session,
            user,
            text,
            request=request,
            provider_binding=provider_binding,
        )


def _planner_fallback_turn(
    session: ChatSession,
    user,
    text: str,
    *,
    request=None,
    provider_binding: dict[str, Any] | None = None,
) -> AssistantTurnResult:
    """Legacy v1 flow: one planner call proposing actions (no tool loop)."""
    with transaction.atomic():
        user_message = ChatMessage.objects.create(session=session, role=ChatMessage.ROLE_USER, content=text)
        session.title = (session.title if session.messages.count() > 1 else text[:80]) or session.title
        session.save(update_fields=["title", "updated_at"])

    try:
        history = _chat_history(session)
        catalog = _action_catalog_for_user(user)
        runtime_context = build_runtime_context(user)
        from core_ui.services.operator_provider_context import prepare_operator_turn_context

        execution_context = replace(
            prepare_operator_turn_context(
                session=session,
                user=user,
                provider_binding=provider_binding,
            ),
            idempotency_key=f"chat:{session.pk}:legacy-planner:{user_message.pk}",
        )
        plan = asyncio.run(
            _call_planner(
                history=history,
                catalog=catalog,
                runtime_context=runtime_context,
                message=text,
                execution_context=execution_context,
            )
        )
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
        metadata={"actions": [action.action_type for action in actions], "source": "planner_fallback"},
    )
    return AssistantTurnResult(user_message=user_message, assistant_message=assistant_message, actions=actions)


def _operator_error_turn(
    session: ChatSession,
    user,
    text: str,
    error: str,
    *,
    request=None,
) -> AssistantTurnResult:
    """Create user + assistant error so the UI never shows a silent dead-end."""
    with transaction.atomic():
        user_message = ChatMessage.objects.create(session=session, role=ChatMessage.ROLE_USER, content=text)
        if session.messages.count() <= 1 or session.title in {"", "Новый чат"}:
            session.title = text[:80] or session.title
            session.save(update_fields=["title", "updated_at"])
        else:
            session.save(update_fields=["updated_at"])
        reply = (error or "Оператор временно недоступен. Попробуй ещё раз.").strip()[:2000]
        assistant_message = ChatMessage.objects.create(
            session=session,
            role=ChatMessage.ROLE_ASSISTANT,
            content=reply,
            metadata={"source": "operator_error"},
        )
    log_user_activity(
        user=user,
        request=request,
        category="assistant",
        action="chat_message_error",
        status=UserActivityLog.STATUS_ERROR,
        description=text[:400],
        entity_type="chat_session",
        entity_id=str(session.pk),
        metadata={"error": reply[:400]},
    )
    return AssistantTurnResult(user_message=user_message, assistant_message=assistant_message, actions=[])
