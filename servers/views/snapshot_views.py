"""REST API for rollback snapshots (2.4)."""

from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods

from servers.services import snapshot_service


@login_required
@require_http_methods(["GET"])
def snapshot_list(request, server_id: int):
    """GET /servers/<server_id>/snapshots/ — list recent snapshots."""
    snapshots = snapshot_service.list_snapshots(
        server_id=server_id,
        user_id=request.user.id,
        limit=int(request.GET.get("limit", 30)),
    )
    return JsonResponse({"snapshots": snapshots})


@login_required
@require_http_methods(["GET"])
def snapshot_detail(request, server_id: int, snapshot_id: int):
    """GET /servers/<server_id>/snapshots/<id>/ — full snapshot with content."""
    detail = snapshot_service.get_snapshot_detail(snapshot_id)
    if not detail or detail["server_id"] != server_id:
        return JsonResponse({"error": "not found"}, status=404)
    if detail["user_id"] != request.user.id and not request.user.is_staff:
        return JsonResponse({"error": "forbidden"}, status=403)
    return JsonResponse({"snapshot": detail})


@login_required
@require_http_methods(["POST"])
def snapshot_restore(request, server_id: int, snapshot_id: int):
    """POST /servers/<server_id>/snapshots/<id>/restore/ — get restore cmd."""
    detail = snapshot_service.get_snapshot_detail(snapshot_id)
    if not detail or detail["server_id"] != server_id:
        return JsonResponse({"error": "not found"}, status=404)
    if detail["user_id"] != request.user.id and not request.user.is_staff:
        return JsonResponse({"error": "forbidden"}, status=403)
    cmd = snapshot_service.build_restore_command(snapshot_id)
    if not cmd:
        return JsonResponse({"error": "cannot restore"}, status=400)
    return JsonResponse({"restore_command": cmd})
