"""
Server memory HTTP endpoints.

This module owns user-facing memory snapshot actions and staff-only memory
operations. The durable memory implementation stays behind the memory store
adapter; views only validate access, parse request payloads, and serialize
responses.
"""

import json

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_http_methods

from app.agent_kernel.memory.repair import compute_freshness_score
from core_ui.access import feature_allowed_for_user
from core_ui.decorators import require_feature
from servers.adapters.memory_store import DjangoServerMemoryStore
from servers.models import Server, ServerMemorySnapshot


def _json_body(request) -> dict:
    return json.loads(request.body or "{}")


def _staff_required_response(request):
    if request.user.is_staff:
        return None
    return JsonResponse({"success": False, "error": "Forbidden"}, status=403)


def _get_owned_server(request, server_id: int) -> Server:
    return get_object_or_404(Server, id=server_id, user=request.user)


def _memory_overview_payload(store: DjangoServerMemoryStore, server_id: int) -> dict:
    return {"success": True, **store._get_memory_overview_sync(server_id)}


def _snapshot_kind(memory_key: str) -> str:
    if memory_key.startswith("pattern_candidate:"):
        return "pattern"
    if memory_key.startswith("automation_candidate:"):
        return "automation"
    if memory_key.startswith("skill_draft:"):
        return "skill_draft"
    if memory_key.startswith("llm_candidate:"):
        return "llm_candidate"
    if memory_key.startswith("manual_note:"):
        return "manual_note"
    if memory_key.startswith("knowledge_note:"):
        return "ai_note"
    return "canonical"


def _serialize_user_snapshot(snapshot: ServerMemorySnapshot) -> dict:
    memory_key = snapshot.memory_key or ""
    metadata = dict(snapshot.metadata or {})
    rewrite_reason = str(metadata.get("rewrite_reason") or metadata.get("superseded_reason") or "").strip()
    freshness = compute_freshness_score(snapshot.updated_at, snapshot.last_verified_at)
    return {
        "id": snapshot.id,
        "title": snapshot.title or memory_key,
        "content": snapshot.content or "",
        "memory_key": memory_key,
        "kind": _snapshot_kind(memory_key),
        "version": snapshot.version,
        "confidence": float(snapshot.confidence or 0),
        "freshness": float(freshness or 0),
        "updated_at": snapshot.updated_at.isoformat() if snapshot.updated_at else None,
        "created_at": snapshot.created_at.isoformat() if snapshot.created_at else None,
        "rewrite_reason": rewrite_reason,
    }


@login_required
@require_feature("servers")
@require_http_methods(["GET"])
def server_memory_snapshots_user(request, server_id):
    """Return canonical and candidate snapshots for a user's Knowledge tab."""
    server = _get_owned_server(request, server_id)
    snapshots = ServerMemorySnapshot.objects.filter(
        server_id=server.id,
        is_active=True,
        archived_at__isnull=True,
    ).order_by("memory_key")
    return JsonResponse(
        {
            "success": True,
            "items": [_serialize_user_snapshot(snapshot) for snapshot in snapshots],
        }
    )


@login_required
@require_feature("servers")
@require_http_methods(["POST"])
def server_memory_snapshot_update(request, server_id, snapshot_id):
    """Edit a snapshot title/content from the user-facing Knowledge tab."""
    server = _get_owned_server(request, server_id)
    snapshot = get_object_or_404(
        ServerMemorySnapshot,
        id=snapshot_id,
        server_id=server.id,
        is_active=True,
        archived_at__isnull=True,
    )
    data = _json_body(request)
    changed = False

    new_title = data.get("title")
    if new_title is not None:
        snapshot.title = str(new_title).strip()[:200]
        changed = True

    new_content = data.get("content")
    if new_content is not None:
        snapshot.content = str(new_content).strip()[:8000]
        changed = True

    if changed:
        snapshot.save(update_fields=["title", "content", "updated_at"])

    return JsonResponse(
        {
            "success": True,
            "id": snapshot.id,
            "title": snapshot.title,
            "content": snapshot.content,
            "updated_at": snapshot.updated_at.isoformat() if snapshot.updated_at else None,
        }
    )


@login_required
@require_feature("servers")
@require_http_methods(["POST"])
def server_memory_snapshot_delete_user(request, server_id, snapshot_id):
    server = _get_owned_server(request, server_id)
    store = DjangoServerMemoryStore()
    try:
        deleted = store._hard_delete_snapshot_sync(
            server.id,
            snapshot_id,
            actor_user_id=request.user.id,
        )
    except ValueError as exc:
        return JsonResponse({"success": False, "error": str(exc)}, status=404)

    purged_all_ai_memory = False
    if not store._has_active_user_ai_snapshots_sync(server.id):
        store._purge_server_ai_memory_sync(server.id, actor_user_id=request.user.id)
        purged_all_ai_memory = True

    return JsonResponse(
        {
            "success": True,
            "deleted": deleted,
            "purged_all_ai_memory": purged_all_ai_memory,
        }
    )


@login_required
@require_feature("servers")
@require_http_methods(["POST"])
def server_memory_snapshots_bulk_delete_user(request, server_id):
    server = _get_owned_server(request, server_id)
    raw_ids = _json_body(request).get("snapshot_ids") or []
    snapshot_ids: list[int] = []
    for value in raw_ids:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            continue
        if parsed > 0 and parsed not in snapshot_ids:
            snapshot_ids.append(parsed)

    if not snapshot_ids:
        return JsonResponse(
            {"success": False, "error": "No snapshots selected"},
            status=400,
        )

    active_snapshot_ids = list(
        ServerMemorySnapshot.objects.filter(
            server_id=server.id,
            id__in=snapshot_ids,
            is_active=True,
            archived_at__isnull=True,
        ).values_list("id", flat=True)
    )

    if not active_snapshot_ids:
        return JsonResponse(
            {"success": False, "error": "No active snapshots found"},
            status=404,
        )

    store = DjangoServerMemoryStore()
    deleted_ids: list[int] = []
    purged_all_ai_memory = False
    for current_id in active_snapshot_ids:
        try:
            store._hard_delete_snapshot_sync(
                server.id,
                current_id,
                actor_user_id=request.user.id,
            )
        except ValueError:
            continue
        deleted_ids.append(current_id)

    if deleted_ids and not store._has_active_user_ai_snapshots_sync(server.id):
        store._purge_server_ai_memory_sync(server.id, actor_user_id=request.user.id)
        purged_all_ai_memory = True

    return JsonResponse(
        {
            "success": True,
            "deleted_count": len(deleted_ids),
            "snapshot_ids": deleted_ids,
            "purged_all_ai_memory": purged_all_ai_memory,
        }
    )


@login_required
@require_feature("servers")
@require_http_methods(["POST"])
def server_memory_purge_user(request, server_id):
    server = _get_owned_server(request, server_id)
    result = DjangoServerMemoryStore()._purge_server_ai_memory_sync(
        server.id,
        actor_user_id=request.user.id,
    )
    return JsonResponse({"success": True, **result})


@login_required
@require_feature("servers")
@require_http_methods(["GET"])
def server_memory_overview(request, server_id):
    forbidden = _staff_required_response(request)
    if forbidden:
        return forbidden

    server = _get_owned_server(request, server_id)
    return JsonResponse(_memory_overview_payload(DjangoServerMemoryStore(), server.id))


@login_required
@require_feature("servers")
@require_http_methods(["POST"])
def server_memory_run_dreams(request, server_id):
    forbidden = _staff_required_response(request)
    if forbidden:
        return forbidden

    server = _get_owned_server(request, server_id)
    data = _json_body(request)
    job_kind = str(data.get("job_kind") or "hybrid").strip().lower()
    if job_kind not in {"nearline", "nightly", "weekly", "hybrid"}:
        job_kind = "hybrid"

    store = DjangoServerMemoryStore()
    result = store._run_dream_cycle_sync(server.id, job_kind=job_kind, force=True)
    return JsonResponse(
        {
            "success": True,
            "job_kind": job_kind,
            "result": result,
            "overview": _memory_overview_payload(store, server.id),
        }
    )


@login_required
@require_feature("servers")
@require_http_methods(["POST"])
def server_memory_policy_update(request, server_id):
    forbidden = _staff_required_response(request)
    if forbidden:
        return forbidden

    server = _get_owned_server(request, server_id)
    store = DjangoServerMemoryStore()
    policy = store._get_or_create_policy_sync(user_id=request.user.id)
    data = _json_body(request)

    dream_mode = str(data.get("dream_mode") or policy.dream_mode).strip().lower()
    allowed_modes = {
        policy.DREAM_HEURISTIC,
        policy.DREAM_NIGHTLY_LLM,
        policy.DREAM_HYBRID,
    }
    if dream_mode not in allowed_modes:
        dream_mode = policy.dream_mode

    policy.dream_mode = dream_mode
    policy.nightly_model_alias = (
        str(data.get("nightly_model_alias") or policy.nightly_model_alias or "opssummary").strip() or "opssummary"
    )
    policy.nearline_event_threshold = max(
        2,
        min(
            int(data.get("nearline_event_threshold") or policy.nearline_event_threshold or 6),
            50,
        ),
    )
    policy.sleep_start_hour = max(
        0,
        min(
            int(data.get("sleep_start_hour") if data.get("sleep_start_hour") is not None else policy.sleep_start_hour),
            23,
        ),
    )
    policy.sleep_end_hour = max(
        0,
        min(
            int(data.get("sleep_end_hour") if data.get("sleep_end_hour") is not None else policy.sleep_end_hour),
            23,
        ),
    )
    policy.raw_event_retention_days = max(
        7,
        min(
            int(data.get("raw_event_retention_days") or policy.raw_event_retention_days or 30),
            365,
        ),
    )
    policy.episode_retention_days = max(
        14,
        min(
            int(data.get("episode_retention_days") or policy.episode_retention_days or 90),
            365,
        ),
    )
    if "human_habits_capture_enabled" in data:
        policy.human_habits_capture_enabled = bool(data.get("human_habits_capture_enabled"))
    if "is_enabled" in data:
        policy.is_enabled = bool(data.get("is_enabled"))
    policy.save()

    return JsonResponse(
        {
            "success": True,
            "overview": _memory_overview_payload(store, server.id),
        }
    )


@login_required
@require_feature("servers")
@require_http_methods(["POST"])
def server_memory_snapshot_archive(request, server_id, snapshot_id):
    forbidden = _staff_required_response(request)
    if forbidden:
        return forbidden

    server = _get_owned_server(request, server_id)
    store = DjangoServerMemoryStore()
    try:
        snapshot = store._archive_snapshot_sync(
            server.id,
            snapshot_id,
            actor_user_id=request.user.id,
        )
    except ValueError as exc:
        return JsonResponse({"success": False, "error": str(exc)}, status=404)

    return JsonResponse(
        {
            "success": True,
            "snapshot": snapshot,
            "overview": _memory_overview_payload(store, server.id),
        }
    )


@login_required
@require_feature("servers")
@require_http_methods(["POST"])
def server_memory_snapshot_promote_note(request, server_id, snapshot_id):
    forbidden = _staff_required_response(request)
    if forbidden:
        return forbidden

    server = _get_owned_server(request, server_id)
    store = DjangoServerMemoryStore()
    try:
        result = store._promote_snapshot_to_manual_knowledge_sync(
            server.id,
            snapshot_id,
            actor_user_id=request.user.id,
        )
    except ValueError as exc:
        return JsonResponse({"success": False, "error": str(exc)}, status=400)
    return JsonResponse({"success": True, **result})


@login_required
@require_feature("servers")
@require_http_methods(["POST"])
def server_memory_snapshot_promote_skill(request, server_id, snapshot_id):
    forbidden = _staff_required_response(request)
    if forbidden:
        return forbidden

    if not feature_allowed_for_user(request.user, "studio_skills"):
        return JsonResponse(
            {"success": False, "error": "Studio skills feature is required"},
            status=403,
        )

    server = _get_owned_server(request, server_id)
    store = DjangoServerMemoryStore()
    try:
        result = store._promote_skill_draft_to_skill_sync(
            server.id,
            snapshot_id,
            actor_user_id=request.user.id,
        )
    except ValueError as exc:
        return JsonResponse({"success": False, "error": str(exc)}, status=400)
    return JsonResponse({"success": True, **result})
