from __future__ import annotations

import json

from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from loguru import logger

from app.assistant_actions import AssistantActionError
from core_ui.decorators import require_feature
from core_ui.models import AssistantAction
from core_ui.services.assistant_chat import (
    cancel_action,
    create_chat_session,
    execute_action,
    get_chat_session,
    handle_user_message,
    list_chat_sessions,
    serialize_action,
    serialize_chat_session,
    serialize_message,
)

# require_http_methods used by duty/artifacts endpoints


def _json_body(request) -> dict:
    try:
        data = json.loads(request.body or "{}")
    except (json.JSONDecodeError, UnicodeDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _err(message: str, status: int = 400) -> JsonResponse:
    return JsonResponse({"error": message}, status=status)


@require_feature("orchestrator")
def api_assistant_chats(request):
    if request.method == "GET":
        return JsonResponse({"chats": list_chat_sessions(request.user)})

    if request.method == "POST":
        data = _json_body(request)
        session = create_chat_session(request.user, title=str(data.get("title") or ""))
        return JsonResponse(serialize_chat_session(session, include_messages=True), status=201)

    return _err("Method not allowed", 405)


@require_feature("orchestrator")
@require_http_methods(["GET", "POST", "PATCH"])
def api_assistant_artifacts(request, chat_id: int):
    from core_ui.services.operator_artifacts import (
        create_artifact,
        get_artifact_for_user,
        list_artifacts,
        serialize_artifact,
        update_artifact_content,
    )

    session = get_chat_session(request.user, chat_id)
    if session is None:
        return _err("Chat not found", 404)

    if request.method == "GET":
        return JsonResponse({"artifacts": list_artifacts(session)})

    data = _json_body(request)
    from core_ui.services.operator_rate_limit import MAX_ARTIFACT_CHARS

    if "content" in data and len(str(data.get("content") or "")) > MAX_ARTIFACT_CHARS:
        return _err(f"Artifact is too large (max {MAX_ARTIFACT_CHARS} characters).", 413)
    if request.method == "POST":
        art = create_artifact(
            session=session,
            kind=str(data.get("kind") or "other"),
            title=str(data.get("title") or "Artifact"),
            content=str(data.get("content") or ""),
            metadata=data.get("metadata") if isinstance(data.get("metadata"), dict) else {},
        )
        return JsonResponse(serialize_artifact(art), status=201)

    # PATCH — update existing
    artifact_id = int(data.get("id") or 0)
    art = get_artifact_for_user(request.user, artifact_id)
    if art is None or art.session_id != session.pk:
        return _err("Artifact not found", 404)
    art = update_artifact_content(
        art,
        content=str(data.get("content") if "content" in data else art.content),
        title=str(data["title"]) if "title" in data else None,
        bump_version=bool(data.get("bump_version", True)),
    )
    return JsonResponse(serialize_artifact(art))


@require_feature("orchestrator")
def api_assistant_duty(request):
    """Get/create duty session, toggle enabled, or force a briefing."""
    from core_ui.services.operator_duty import (
        deliver_morning_briefing,
        duty_enabled,
        get_or_create_duty_session,
        set_duty_enabled,
    )

    if request.method == "GET":
        session = get_or_create_duty_session(request.user)
        return JsonResponse(
            {
                **serialize_chat_session(session, include_messages=True),
                "duty_enabled": duty_enabled(session),
            }
        )

    if request.method == "POST":
        data = _json_body(request)
        if "enabled" in data:
            session = set_duty_enabled(request.user, enabled=bool(data.get("enabled")))
            return JsonResponse(
                {
                    **serialize_chat_session(session),
                    "duty_enabled": duty_enabled(session),
                }
            )
        if data.get("brief_now"):
            result = deliver_morning_briefing(request.user, force=True)
            session = get_or_create_duty_session(request.user)
            return JsonResponse(
                {
                    "ok": True,
                    "result": result,
                    "chat": serialize_chat_session(session, include_messages=True),
                }
            )
        session = get_or_create_duty_session(request.user)
        return JsonResponse(serialize_chat_session(session, include_messages=True), status=201)

    return _err("Method not allowed", 405)


@require_feature("orchestrator")
def api_assistant_chat_detail(request, chat_id: int):
    session = get_chat_session(request.user, chat_id)
    if session is None:
        return _err("Chat not found", 404)

    if request.method == "GET":
        return JsonResponse(serialize_chat_session(session, include_messages=True))

    if request.method == "PATCH":
        data = _json_body(request)
        update_fields: list[str] = []
        if "title" in data:
            session.title = str(data.get("title") or session.title).strip()[:200] or session.title
            update_fields.append("title")
        if "pinned_context" in data and isinstance(data.get("pinned_context"), dict):
            session.pinned_context = data["pinned_context"]
            update_fields.append("pinned_context")
        if "kind" in data:
            kind = str(data.get("kind") or "").strip()
            if kind in {"manual", "duty", "incident"}:
                session.kind = kind
                update_fields.append("kind")
        if update_fields:
            update_fields.append("updated_at")
            session.save(update_fields=update_fields)
        return JsonResponse(serialize_chat_session(session, include_messages=False))

    if request.method == "DELETE":
        session.delete()
        return JsonResponse({"ok": True})

    return _err("Method not allowed", 405)


@require_feature("orchestrator")
@require_http_methods(["POST"])
def api_assistant_chat_message(request, chat_id: int):
    session = get_chat_session(request.user, chat_id)
    if session is None:
        return _err("Chat not found", 404)

    data = _json_body(request)
    message = str(data.get("message") or "").strip()
    if not message:
        return _err("message is required")
    from core_ui.services.operator_rate_limit import MAX_MESSAGE_CHARS

    if len(message) > MAX_MESSAGE_CHARS:
        return _err(f"Message is too large (max {MAX_MESSAGE_CHARS} characters).", 413)

    try:
        result = handle_user_message(session, request.user, message, request=request)
    except AssistantActionError as exc:
        return _err(exc.message, exc.status)
    except Exception as exc:
        return _err(str(exc), 400)

    return JsonResponse(
        {
            "chat": serialize_chat_session(session),
            "user_message": serialize_message(result.user_message),
            "assistant_message": serialize_message(result.assistant_message),
            "actions": [serialize_action(action) for action in result.actions],
        },
        status=201,
    )


@require_feature("orchestrator")
@require_http_methods(["POST"])
def api_assistant_chat_create_and_message(request):
    data = _json_body(request)
    message = str(data.get("message") or "").strip()
    if not message:
        return _err("message is required")
    from core_ui.services.operator_rate_limit import MAX_MESSAGE_CHARS

    if len(message) > MAX_MESSAGE_CHARS:
        return _err(f"Message is too large (max {MAX_MESSAGE_CHARS} characters).", 413)
    session = create_chat_session(request.user, title=message[:80])
    try:
        result = handle_user_message(session, request.user, message, request=request)
    except AssistantActionError as exc:
        session.delete()
        return _err(exc.message, exc.status)
    except Exception as exc:
        return _err(str(exc), 400)
    return JsonResponse(
        {
            "chat": serialize_chat_session(session),
            "user_message": serialize_message(result.user_message),
            "assistant_message": serialize_message(result.assistant_message),
            "actions": [serialize_action(action) for action in result.actions],
        },
        status=201,
    )


def _get_action_for_user(user, action_id: int) -> AssistantAction | None:
    return AssistantAction.objects.select_related("session", "message", "user").filter(pk=action_id, user=user).first()


def _resume_operator_if_parked(action: AssistantAction, *, request=None, cancelled: bool = False) -> None:
    """Best-effort resume of operator loop after confirm/cancel."""
    try:
        import asyncio

        from core_ui.services.operator_loop import resume_after_action

        async def _run():
            await resume_after_action(action=action, request=request, cancelled=cancelled)

        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures

                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                    pool.submit(lambda: asyncio.run(_run())).result(timeout=180)
            else:
                loop.run_until_complete(_run())
        except RuntimeError:
            asyncio.run(_run())
    except Exception as exc:  # noqa: BLE001 — confirm must still return action result
        logger.warning("assistant action resume failed action_id={}: {}", action.pk, exc)


@require_feature("orchestrator")
@require_http_methods(["POST"])
def api_assistant_action_confirm(request, action_id: int):
    action = _get_action_for_user(request.user, action_id)
    if action is None:
        return _err("Action not found", 404)
    if action.status in {AssistantAction.STATUS_COMPLETED, AssistantAction.STATUS_RUNNING}:
        return JsonResponse(serialize_action(action))
    if action.status in {AssistantAction.STATUS_CANCELLED, AssistantAction.STATUS_FAILED}:
        return _err(f"Action is {action.status}", 409)
    data = _json_body(request)
    typed_confirm = str(data.get("typed_confirm") or data.get("confirm_token") or "").strip() or None
    action = execute_action(action, request=request, confirmed=True, typed_confirm=typed_confirm)
    if action.status == AssistantAction.STATUS_RUNNING:
        # Another worker won the atomic execution claim. It owns both execution
        # and turn resume; this request must not feed an incomplete result to LLM.
        return JsonResponse(serialize_action(action), status=202)
    if action.status == AssistantAction.STATUS_REQUIRES_CONFIRMATION and action.error:
        return JsonResponse(serialize_action(action), status=400)
    _resume_operator_if_parked(action, request=request, cancelled=False)
    # Re-fetch message content after possible resume
    action.refresh_from_db()
    status = 200 if action.status == AssistantAction.STATUS_COMPLETED else 400
    return JsonResponse(serialize_action(action), status=status)


@require_feature("orchestrator")
@require_http_methods(["POST"])
def api_assistant_action_cancel(request, action_id: int):
    action = _get_action_for_user(request.user, action_id)
    if action is None:
        return _err("Action not found", 404)
    action = cancel_action(action)
    _resume_operator_if_parked(action, request=request, cancelled=True)
    return JsonResponse(serialize_action(action))
