"""Playbook run lifecycle views (execute / list / detail / cancel / rerun).

Extracted from server_playbooks.py to keep modules under the size limit.
Re-exported from servers.views.server_playbooks so URL routing stays stable.
"""

from __future__ import annotations

import json

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_http_methods

from core_ui.activity import log_user_activity
from core_ui.decorators import require_feature
from core_ui.models import UserActivityLog
from core_ui.projects import active_project_for_user
from servers.models import PlaybookRun
from servers.services.playbook_compatibility_validation import validate_playbook_syntax
from servers.services.playbook_run_preparation import (
    PlaybookRunPreparationError,
    prepare_playbook_run,
)
from servers.services.playbook_runner import start_playbook_run_async
from servers.views.server_helpers import _effective_master_password
from servers.views.server_playbook_serializers import _playbooks_for_user, _serialize_run


@login_required
@require_feature("servers")
@require_http_methods(["POST"])
def playbook_run(request, playbook_id: int):
    pb = get_object_or_404(_playbooks_for_user(request.user), id=playbook_id)
    data = json.loads(request.body or "{}")
    master_password = _effective_master_password(request, data)
    try:
        prepared = prepare_playbook_run(
            user=request.user,
            playbook=pb,
            payload=data,
            syntax_validator=validate_playbook_syntax,
            enqueue_master_password=master_password,
        )
    except PlaybookRunPreparationError as exc:
        body = {"success": False, "error": exc.message}
        if exc.compatibility:
            body["compatibility"] = exc.compatibility
        return JsonResponse(body, status=exc.status)

    run = prepared.run
    servers = prepared.servers
    start_playbook_run_async(run.id, master_password=master_password)

    log_user_activity(
        user=request.user,
        request=request,
        category="servers",
        action="playbook_run",
        status=UserActivityLog.STATUS_SUCCESS,
        description=f'Started playbook run "{pb.name}" on {len(servers)} host(s)',
        entity_type="playbook_run",
        entity_id=run.id,
        entity_name=pb.name,
        metadata={"hosts": len(servers), "dry_run": bool((run.options or {}).get("dry_run"))},
    )

    return JsonResponse({"success": True, "run": _serialize_run(run, include_hosts=True)})


@login_required
@require_feature("servers")
@require_http_methods(["GET"])
def playbook_run_list(request):
    qs = PlaybookRun.objects.filter(user=request.user, project=active_project_for_user(request.user)).order_by(
        "-created_at"
    )[:50]
    return JsonResponse(
        {
            "success": True,
            "runs": [_serialize_run(r, include_hosts=False) for r in qs],
        }
    )


@login_required
@require_feature("servers")
@require_http_methods(["GET"])
def playbook_run_detail(request, run_id: int):
    run = get_object_or_404(PlaybookRun, id=run_id, user=request.user, project=active_project_for_user(request.user))
    return JsonResponse({"success": True, "run": _serialize_run(run, include_hosts=True)})


@login_required
@require_feature("servers")
@require_http_methods(["POST"])
def playbook_run_cancel(request, run_id: int):
    run = get_object_or_404(PlaybookRun, id=run_id, user=request.user, project=active_project_for_user(request.user))
    if run.status in (
        PlaybookRun.STATUS_COMPLETED,
        PlaybookRun.STATUS_FAILED,
        PlaybookRun.STATUS_PARTIAL,
        PlaybookRun.STATUS_CANCELLED,
    ):
        return JsonResponse({"success": True, "run": _serialize_run(run), "message": "Run already finished"})
    from servers.playbooks.dispatch import cancel_playbook_dispatch_for_run

    cancel_playbook_dispatch_for_run(run.id, reason="user_requested")
    run.refresh_from_db()
    return JsonResponse({"success": True, "run": _serialize_run(run)})


@login_required
@require_feature("servers")
@require_http_methods(["POST"])
def playbook_run_rerun_failed(request, run_id: int):
    """Re-run failed targets through the same exact-revision preflight."""
    prev = get_object_or_404(PlaybookRun, id=run_id, user=request.user, project=active_project_for_user(request.user))
    host_results = prev.host_results if isinstance(prev.host_results, list) else []
    failed_ids = [
        int(h["server_id"])
        for h in host_results
        if h.get("status") in ("error", "failed", "partial") and h.get("server_id") is not None
    ]
    if not failed_ids:
        return JsonResponse({"success": False, "error": "No failed hosts to re-run"}, status=400)

    if prev.playbook is None or prev.revision_id is None:
        return JsonResponse(
            {"success": False, "error": "Original run has no immutable revision; start a new preflight"},
            status=409,
        )
    data = json.loads(request.body or "{}")
    old_snapshot = prev.playbook_snapshot if isinstance(prev.playbook_snapshot, dict) else {}
    old_options = prev.options if isinstance(prev.options, dict) else {}
    raw_bindings = (
        old_snapshot.get("inventory_bindings") if isinstance(old_snapshot.get("inventory_bindings"), dict) else {}
    )
    failed_set = set(failed_ids)
    filtered_bindings = {
        selector: {
            "server_ids": [int(item) for item in (binding.get("server_ids") or []) if int(item) in failed_set],
            "group_ids": [],
        }
        for selector, binding in raw_bindings.items()
        if isinstance(binding, dict)
    }
    payload = {
        "revision_id": prev.revision_id,
        "binding_profile_id": prev.binding_profile_id,
        "server_ids": failed_ids,
        "inventory_bindings": filtered_bindings,
        "engine": old_options.get("engine") or "ansible",
        "concurrency": old_options.get("concurrency") or 4,
        "dry_run": bool(old_options.get("dry_run")),
        "become": bool(old_options.get("become", True)),
        "tags": old_options.get("tags") or "",
        "skip_tags": old_options.get("skip_tags") or "",
        "limit": old_options.get("limit") or "",
        "extra_vars": data.get("extra_vars") if isinstance(data.get("extra_vars"), dict) else {},
    }
    master_password = _effective_master_password(request, data)
    try:
        prepared = prepare_playbook_run(
            user=request.user,
            playbook=prev.playbook,
            payload=payload,
            enqueue_master_password=master_password,
        )
    except PlaybookRunPreparationError as exc:
        body = {"success": False, "error": exc.message}
        if exc.compatibility:
            body["compatibility"] = exc.compatibility
        return JsonResponse(body, status=exc.status)
    run = prepared.run
    run.options = dict(run.options or {}) | {"rerun_of": prev.id}
    run.save(update_fields=["options"])
    start_playbook_run_async(run.id, master_password=master_password)
    return JsonResponse({"success": True, "run": _serialize_run(run)})
