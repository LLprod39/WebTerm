"""
Server knowledge HTTP endpoints.

These endpoints back the server edit modal's knowledge tab. They keep manual
knowledge rows in sync with layered-memory manual snapshots via the memory store
adapter.
"""

import json

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_http_methods
from loguru import logger

from core_ui.api_failure import internal_error_response
from core_ui.decorators import require_feature
from servers.adapters.memory_store import DjangoServerMemoryStore
from servers.models import Server, ServerKnowledge


def _json_body(request) -> dict:
    return json.loads(request.body or "{}")


def _get_owned_server(request, server_id: int) -> Server:
    return get_object_or_404(Server, id=server_id, user=request.user)


def _valid_categories() -> set[str]:
    return {value for value, _label in ServerKnowledge.CATEGORY_CHOICES}


def _serialize_knowledge(knowledge: ServerKnowledge) -> dict:
    return {
        "id": knowledge.id,
        "title": knowledge.title,
        "content": knowledge.content,
        "category": knowledge.category,
        "category_label": knowledge.get_category_display(),
        "source": knowledge.source,
        "source_label": knowledge.get_source_display(),
        "confidence": float(knowledge.confidence or 0.0),
        "is_active": bool(knowledge.is_active),
        "updated_at": knowledge.updated_at.isoformat() if knowledge.updated_at else None,
    }


@login_required
@require_feature("servers")
@require_http_methods(["GET"])
def server_knowledge_list(request, server_id):
    """List AI/manual knowledge items for server edit modal."""
    server = _get_owned_server(request, server_id)
    include_inactive = str(request.GET.get("include_inactive", "") or "").strip().lower() in {"1", "true", "yes"}
    rows_qs = ServerKnowledge.objects.filter(server=server)
    if not include_inactive:
        rows_qs = rows_qs.filter(is_active=True)
    rows = rows_qs.order_by("-updated_at")[:100]
    return JsonResponse(
        {
            "success": True,
            "items": [_serialize_knowledge(knowledge) for knowledge in rows],
            "categories": [{"value": value, "label": label} for value, label in ServerKnowledge.CATEGORY_CHOICES],
            "include_inactive": include_inactive,
        }
    )


@login_required
@require_feature("servers")
@require_http_methods(["POST"])
def server_knowledge_create(request, server_id):
    """Create knowledge entry in edit modal."""
    try:
        server = _get_owned_server(request, server_id)
        data = _json_body(request)
        title = str(data.get("title") or "").strip()
        content = str(data.get("content") or "").strip()
        category = str(data.get("category") or "other").strip()
        is_active = bool(data.get("is_active", True))

        if category not in _valid_categories():
            category = "other"
        if not title:
            return JsonResponse({"success": False, "error": "Title is required"}, status=400)
        if not content:
            return JsonResponse({"success": False, "error": "Content is required"}, status=400)

        knowledge = ServerKnowledge.objects.create(
            server=server,
            category=category,
            title=title[:200],
            content=content[:8000],
            source="manual",
            confidence=1.0,
            is_active=is_active,
            created_by=request.user,
        )
        DjangoServerMemoryStore()._sync_manual_knowledge_snapshot_sync(knowledge.id)
        return JsonResponse({"success": True, "id": knowledge.id})
    except Exception as exc:
        return internal_error_response(request, exc)


@login_required
@require_feature("servers")
@require_http_methods(["POST"])
def server_knowledge_update(request, server_id, knowledge_id):
    """Update title/content/category/flags for knowledge entry."""
    try:
        server = _get_owned_server(request, server_id)
        knowledge = get_object_or_404(ServerKnowledge, id=knowledge_id, server=server)
        data = _json_body(request)

        if "title" in data:
            title = str(data.get("title") or "").strip()
            if not title:
                return JsonResponse({"success": False, "error": "Title is required"}, status=400)
            knowledge.title = title[:200]

        if "content" in data:
            content = str(data.get("content") or "").strip()
            if not content:
                return JsonResponse({"success": False, "error": "Content is required"}, status=400)
            knowledge.content = content[:8000]

        if "category" in data:
            category = str(data.get("category") or "").strip()
            if category in _valid_categories():
                knowledge.category = category

        if "is_active" in data:
            knowledge.is_active = bool(data.get("is_active"))

        if "confidence" in data:
            try:
                confidence = float(data.get("confidence"))
                knowledge.confidence = max(0.0, min(1.0, confidence))
            except (TypeError, ValueError) as exc:
                logger.debug("invalid knowledge confidence ignored: {}", exc)

        knowledge.save()
        DjangoServerMemoryStore()._sync_manual_knowledge_snapshot_sync(knowledge.id)
        return JsonResponse({"success": True})
    except Exception as exc:
        return internal_error_response(request, exc)


@login_required
@require_feature("servers")
@require_http_methods(["POST"])
def server_knowledge_delete(request, server_id, knowledge_id):
    """Delete knowledge entry."""
    try:
        server = _get_owned_server(request, server_id)
        knowledge = get_object_or_404(ServerKnowledge, id=knowledge_id, server=server)
        DjangoServerMemoryStore()._archive_manual_knowledge_snapshot_sync(knowledge.id)
        knowledge.delete()
        return JsonResponse({"success": True})
    except Exception as exc:
        return internal_error_response(request, exc)
