from __future__ import annotations

import json

from django.http import JsonResponse
from django.views.decorators.http import require_http_methods

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
def api_assistant_chat_detail(request, chat_id: int):
    session = get_chat_session(request.user, chat_id)
    if session is None:
        return _err("Chat not found", 404)

    if request.method == "GET":
        return JsonResponse(serialize_chat_session(session, include_messages=True))

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

    try:
        result = handle_user_message(session, request.user, message, request=request)
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
    session = create_chat_session(request.user, title=message[:80])
    try:
        result = handle_user_message(session, request.user, message, request=request)
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
    action = execute_action(action, request=request, confirmed=True)
    status = 200 if action.status == AssistantAction.STATUS_COMPLETED else 400
    return JsonResponse(serialize_action(action), status=status)


@require_feature("orchestrator")
@require_http_methods(["POST"])
def api_assistant_action_cancel(request, action_id: int):
    action = _get_action_for_user(request.user, action_id)
    if action is None:
        return _err("Action not found", 404)
    action = cancel_action(action)
    return JsonResponse(serialize_action(action))
