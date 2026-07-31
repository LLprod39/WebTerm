"""
Chat session APIs and streaming assistant endpoint.
"""

import asyncio
import json

from asgiref.sync import async_to_sync, sync_to_async
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.db.models import Count, OuterRef, Subquery
from django.http import JsonResponse, StreamingHttpResponse
from django.views.decorators.http import require_http_methods
from loguru import logger

from app.core.model_config import model_manager
from core_ui.activity import log_user_activity
from core_ui.api_errors import internal_error_response
from core_ui.decorators import async_login_required, async_require_feature, require_feature
from core_ui.models import ChatMessage, ChatSession, UserActivityLog
from core_ui.views.chat_helpers import (
    _chat_history_from_session,
    _get_servers_context_for_prompt,
    _load_session,
    _load_task_context_for_user,
    _stream_cursor_cli,
    _try_server_command_by_name,
)
from core_ui.views.ide_views import _resolve_ide_workspace
from core_ui.views.runtime import get_unified_orchestrator


@login_required
@require_feature("orchestrator")
@require_http_methods(["GET"])
def api_chats_list(request):
    """List current user's chat sessions."""
    try:
        last_msg_qs = ChatMessage.objects.filter(session=OuterRef("pk")).order_by("-created_at")
        sessions = (
            ChatSession.objects.filter(user=request.user)
            .annotate(
                last_message=Subquery(last_msg_qs.values("content")[:1]),
                last_message_role=Subquery(last_msg_qs.values("role")[:1]),
                last_message_at=Subquery(last_msg_qs.values("created_at")[:1]),
                message_count=Count("messages"),
            )
            .order_by("-updated_at")[:50]
        )

        def _preview(text):
            if not text:
                return ""
            cleaned = " ".join(str(text).split())
            return (cleaned[:140] + "...") if len(cleaned) > 140 else cleaned

        items = []
        for session in sessions:
            items.append(
                {
                    "id": session.id,
                    "title": session.title,
                    "created_at": session.created_at.isoformat(),
                    "updated_at": session.updated_at.isoformat(),
                    "preview": _preview(getattr(session, "last_message", "")),
                    "last_message_role": getattr(session, "last_message_role", None),
                    "last_message_at": (
                        session.last_message_at.isoformat() if getattr(session, "last_message_at", None) else None
                    ),
                    "message_count": session.message_count or 0,
                }
            )
        return JsonResponse({"chats": items})
    except Exception as exc:
        logger.error(f"api_chats_list: {exc}")
        return internal_error_response(request, exc)


@login_required
@require_feature("orchestrator")
@require_http_methods(["POST"])
def api_chats_create(request):
    """Create a new chat session."""
    try:
        data = json.loads(request.body) if request.body else {}
        title = (data.get("title") or "").strip() or "Новый чат"
        session = ChatSession.objects.create(user=request.user, title=title)
        return JsonResponse({"id": session.id, "title": session.title})
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)
    except Exception as exc:
        logger.error(f"api_chats_create: {exc}")
        return internal_error_response(request, exc)


@login_required
@require_feature("orchestrator")
@require_http_methods(["GET"])
def api_chat_detail(request, chat_id):
    """Return one chat session with messages."""
    try:
        session = ChatSession.objects.filter(user=request.user, id=chat_id).first()
        if not session:
            return JsonResponse({"error": "Not found"}, status=404)
        messages = [
            {"role": message.role, "content": message.content, "created_at": message.created_at.isoformat()}
            for message in session.messages.order_by("created_at")
        ]
        return JsonResponse(
            {
                "id": session.id,
                "title": session.title,
                "created_at": session.created_at.isoformat(),
                "updated_at": session.updated_at.isoformat(),
                "messages": messages,
            }
        )
    except Exception as exc:
        logger.error(f"api_chat_detail: {exc}")
        return internal_error_response(request, exc)


@async_login_required
@async_require_feature("orchestrator")
async def chat_api(request):
    """
    Stream assistant chat responses.

    Body: { "message": "...", "model": "auto|gemini|grok|openai|claude|ollama", "chat_id": null|int }
    """
    if request.method != "POST":
        return JsonResponse({"error": "Method not allowed"}, status=405)

    try:
        data = json.loads(request.body)
        user_message = data.get("message", "")
        model = data.get("model", model_manager.config.default_provider)
        specific_model = data.get("specific_model")
        use_rag = data.get("use_rag", True)
        chat_id = data.get("chat_id")
        task_context_id = data.get("task_context_id")
        workspace_param = data.get("workspace", "").strip()

        if not user_message:
            return JsonResponse({"error": "Empty message"}, status=400)

        user_id = await sync_to_async(lambda r: r.user.id if getattr(r.user, "is_authenticated", False) else None)(
            request
        )
        if user_id:
            await sync_to_async(log_user_activity, thread_sensitive=True)(
                user_id=user_id,
                request=request,
                category="assistant",
                action="chat_request",
                status=UserActivityLog.STATUS_SUCCESS,
                description=user_message[:400],
                entity_type="chat_session",
                entity_id=str(chat_id or ""),
                metadata={
                    "model": model,
                    "specific_model": specific_model or "",
                    "use_rag": bool(use_rag),
                    "workspace": workspace_param or "",
                },
            )

        session = None
        initial_history = None
        if chat_id and user_id:
            session = await asyncio.to_thread(_load_session, user_id, chat_id)
            if session:
                initial_history = await asyncio.to_thread(_chat_history_from_session, session)

        task_context = {}
        if task_context_id and user_id:
            task_context = await asyncio.to_thread(_load_task_context_for_user, user_id, task_context_id)

        async def event_stream():
            nonlocal session
            accumulated = []
            created_session_id = None
            try:
                effective_model = model_manager.config.default_provider or "cursor" if model == "auto" else model

                if effective_model in ("cursor", "auto"):
                    if not session and user_id:
                        session = await asyncio.to_thread(
                            lambda: ChatSession.objects.create(
                                user_id=user_id,
                                title=(user_message[:80] or "Чат").strip() or "Чат",
                            )
                        )
                        created_session_id = session.id

                    server_result = await _try_server_command_by_name(user_id, user_message)
                    if server_result is not None:
                        if created_session_id is not None:
                            yield f"CHAT_ID:{created_session_id}\n"
                        yield server_result
                        if user_id and session:
                            await asyncio.to_thread(_save_chat_exchange, session, user_message, server_result)
                        return

                    workspace = getattr(settings, "BASE_DIR", "")
                    cursor_mode = getattr(model_manager.config, "cursor_chat_mode", "ask") or "ask"
                    cursor_sandbox = getattr(model_manager.config, "cursor_sandbox", "") or ""
                    cursor_approve_mcps = getattr(model_manager.config, "cursor_approve_mcps", False)
                    servers_ctx = await asyncio.to_thread(_get_servers_context_for_prompt, user_id) if user_id else ""
                    task_ctx_prompt = _build_task_context_prompt(task_context)
                    prompt_with_servers = (
                        (servers_ctx + "\n\n" + task_ctx_prompt + user_message)
                        if (servers_ctx or task_ctx_prompt)
                        else user_message
                    )
                    if created_session_id is not None:
                        yield f"CHAT_ID:{created_session_id}\n"
                    async for chunk in _stream_cursor_cli(
                        prompt_with_servers,
                        workspace,
                        mode=cursor_mode,
                        sandbox=cursor_sandbox,
                        approve_mcps=cursor_approve_mcps,
                    ):
                        accumulated.append(chunk)
                        yield chunk
                    if user_id and session:
                        await asyncio.to_thread(_save_chat_exchange, session, user_message, "".join(accumulated))
                    return

                if not session and user_id:
                    session = await asyncio.to_thread(
                        lambda: ChatSession.objects.create(
                            user_id=user_id,
                            title=(user_message[:80] or "Новый чат").strip() or "Новый чат",
                        )
                    )
                    created_session_id = session.id
                if created_session_id is not None:
                    yield f"CHAT_ID:{created_session_id}\n"

                workspace_path = None
                if workspace_param:
                    try:
                        workspace_root = await asyncio.to_thread(_resolve_ide_workspace, workspace_param)
                        workspace_path = str(workspace_root)
                    except ValueError as exc:
                        yield f"\n\n❌ Ошибка workspace: {exc}\n"
                        return

                execution_context = _build_execution_context(user_id, task_context, workspace_path)
                use_rag_effective = use_rag if not workspace_path else False
                execution_context["rag_enabled"] = bool(use_rag_effective)

                orchestrator = await get_unified_orchestrator()
                orchestrator_mode = data.get("mode")
                if not orchestrator_mode and not workspace_path:
                    orchestrator_mode = "chat"

                async for chunk in orchestrator.process_user_message(
                    user_message,
                    model_preference=effective_model,
                    use_rag=use_rag_effective,
                    specific_model=specific_model,
                    user_id=user_id,
                    initial_history=initial_history,
                    execution_context=execution_context if execution_context else None,
                    mode=orchestrator_mode,
                ):
                    accumulated.append(chunk)
                    yield chunk
                if user_id and session:
                    await asyncio.to_thread(_save_chat_exchange, session, user_message, "".join(accumulated))
            except FileNotFoundError as exc:
                yield f"\n\n❌ {exc}"
            except Exception as exc:
                yield f"\n\n❌ Error: {str(exc)}"

        return StreamingHttpResponse(event_stream(), content_type="text/plain; charset=utf-8")

    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)
    except Exception as exc:
        return internal_error_response(request, exc)


def _build_task_context_prompt(task_context: dict) -> str:
    if not task_context:
        return ""
    return (
        "TASK CONTEXT:\n"
        f"- id: {task_context.get('id')}\n"
        f"- title: {task_context.get('title')}\n"
        f"- status: {task_context.get('status')}\n"
        f"- priority: {task_context.get('priority')}\n"
        f"- due_date: {task_context.get('due_date')}\n"
        f"- description: {task_context.get('description')}\n"
        "If user asks about 'this task', refer to this context instead of listing all tasks.\n\n"
    )


def _build_execution_context(user_id: int | None, task_context: dict, workspace_path: str | None) -> dict:
    execution_context = {}
    if user_id:
        execution_context["user_id"] = user_id
    if task_context:
        execution_context["task_context"] = task_context
    if workspace_path:
        execution_context["workspace_path"] = workspace_path
        execution_context["from_ide"] = True
    return execution_context


def _save_chat_exchange(session, user_message: str, assistant_message: str) -> None:
    ChatMessage.objects.create(session=session, role=ChatMessage.ROLE_USER, content=user_message)
    ChatMessage.objects.create(session=session, role=ChatMessage.ROLE_ASSISTANT, content=assistant_message)
    session.title = (user_message[:80] or session.title).strip() or session.title
    session.save(update_fields=["title", "updated_at"])


@login_required
@require_feature("orchestrator")
@require_http_methods(["POST"])
def api_clear_history(request):
    """Clear conversation history via UnifiedOrchestrator."""
    try:
        ChatSession.objects.filter(user=request.user).delete()
        orchestrator = async_to_sync(get_unified_orchestrator)()
        orchestrator.clear_history()
        log_user_activity(
            user=request.user,
            request=request,
            category="assistant",
            action="chat_history_clear",
            status=UserActivityLog.STATUS_SUCCESS,
            description="Cleared chat history",
            entity_type="chat",
        )
        return JsonResponse({"success": True, "message": "History cleared"})
    except Exception as exc:
        log_user_activity(
            user=request.user,
            request=request,
            category="assistant",
            action="chat_history_clear",
            status=UserActivityLog.STATUS_ERROR,
            description="Failed to clear chat history (internal_error)",
            entity_type="chat",
        )
        return internal_error_response(request, exc)
