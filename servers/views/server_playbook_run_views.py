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
from servers.models import PlaybookRun, ServerGroup
from servers.services.playbook_runner import (
    build_inventory_for_servers,
    normalize_tasks,
    resolve_target_servers,
    start_playbook_run_async,
)
from servers.views.server_helpers import _effective_master_password, _get_group_role
from servers.views.server_playbook_serializers import _playbooks_for_user, _serialize_run

@login_required
@require_feature("servers")
@require_http_methods(["POST"])
def playbook_run(request, playbook_id: int):
    pb = get_object_or_404(_playbooks_for_user(request.user), id=playbook_id)
    data = json.loads(request.body or "{}")
    server_ids = [int(x) for x in (data.get("server_ids") or []) if str(x).isdigit() or isinstance(x, int)]
    group_ids = [int(x) for x in (data.get("group_ids") or []) if str(x).isdigit() or isinstance(x, int)]

    # Validate group access lightly
    for gid in group_ids:
        group = ServerGroup.objects.filter(id=gid).first()
        if not group:
            continue
        role = _get_group_role(group, request.user)
        if not role and group.user_id != request.user.id:
            # still allow if user has servers in group via ownership
            pass

    servers = resolve_target_servers(request.user, server_ids=server_ids, group_ids=group_ids)
    if not servers:
        return JsonResponse({"success": False, "error": "Select at least one accessible server or group"}, status=400)

    tasks = normalize_tasks(pb.tasks)
    source_yaml = (pb.source_yaml or "").strip()
    if not tasks and not source_yaml:
        return JsonResponse({"success": False, "error": "Playbook has no tasks or Ansible YAML"}, status=400)

    concurrency = int(data.get("concurrency") or 4)
    concurrency = max(1, min(concurrency, 12))
    dry_run = bool(data.get("dry_run"))
    engine = str(data.get("engine") or "ansible").strip().lower()
    if engine not in ("auto", "ansible", "shell"):
        engine = "ansible"
    options = {
        "concurrency": concurrency,
        "dry_run": dry_run,
        "online_only": bool(data.get("online_only", False)),
        "engine": engine,
        "become": bool(data.get("become", True)),
        "tags": str(data.get("tags") or ""),
        "limit": str(data.get("limit") or ""),
        "extra_vars": data.get("extra_vars") if isinstance(data.get("extra_vars"), dict) else {},
    }

    snapshot = {
        "id": pb.id,
        "name": pb.name,
        "description": pb.description,
        "kind": pb.kind,
        "category": pb.category,
        "source_yaml": source_yaml,
        "tasks": [
            {
                "id": t["id"],
                "command": t["command"],
                "description": t.get("description") or "",
                "continue_on_error": bool(t.get("continue_on_error")),
            }
            for t in tasks
        ],
    }

    master_password = _effective_master_password(request, data)

    run = PlaybookRun.objects.create(
        playbook=pb,
        user=request.user,
        status=PlaybookRun.STATUS_PENDING,
        playbook_snapshot=snapshot,
        target_server_ids=[s.id for s in servers],
        target_group_ids=group_ids,
        options=options,
        host_results=[],
        summary={},
        inventory_preview=build_inventory_for_servers(servers),
    )

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
        metadata={"hosts": len(servers), "dry_run": dry_run},
    )

    return JsonResponse({"success": True, "run": _serialize_run(run, include_hosts=True)})


@login_required
@require_feature("servers")
@require_http_methods(["GET"])
def playbook_run_list(request):
    qs = PlaybookRun.objects.filter(user=request.user).order_by("-created_at")[:50]
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
    run = get_object_or_404(PlaybookRun, id=run_id, user=request.user)
    return JsonResponse({"success": True, "run": _serialize_run(run, include_hosts=True)})


@login_required
@require_feature("servers")
@require_http_methods(["POST"])
def playbook_run_cancel(request, run_id: int):
    run = get_object_or_404(PlaybookRun, id=run_id, user=request.user)
    if run.status in (
        PlaybookRun.STATUS_COMPLETED,
        PlaybookRun.STATUS_FAILED,
        PlaybookRun.STATUS_PARTIAL,
        PlaybookRun.STATUS_CANCELLED,
    ):
        return JsonResponse({"success": True, "run": _serialize_run(run), "message": "Run already finished"})
    run.cancel_requested = True
    run.save(update_fields=["cancel_requested"])
    return JsonResponse({"success": True, "run": _serialize_run(run)})


@login_required
@require_feature("servers")
@require_http_methods(["POST"])
def playbook_run_rerun_failed(request, run_id: int):
    """Create a new run targeting only hosts that failed in a previous run."""
    prev = get_object_or_404(PlaybookRun, id=run_id, user=request.user)
    host_results = prev.host_results if isinstance(prev.host_results, list) else []
    failed_ids = [
        int(h["server_id"])
        for h in host_results
        if h.get("status") in ("error", "failed", "partial") and h.get("server_id") is not None
    ]
    if not failed_ids:
        return JsonResponse({"success": False, "error": "No failed hosts to re-run"}, status=400)

    snapshot = prev.playbook_snapshot if isinstance(prev.playbook_snapshot, dict) else {}
    tasks = normalize_tasks(snapshot.get("tasks") or [])
    source_yaml = str(snapshot.get("source_yaml") or "").strip()
    if not tasks and not source_yaml:
        return JsonResponse({"success": False, "error": "Original run has no tasks or Ansible YAML"}, status=400)

    servers = resolve_target_servers(request.user, server_ids=failed_ids, group_ids=[])
    if not servers:
        return JsonResponse({"success": False, "error": "Failed hosts are no longer accessible"}, status=400)

    options = dict(prev.options or {})
    options["rerun_of"] = prev.id
    master_password = _effective_master_password(request, json.loads(request.body or "{}"))

    run = PlaybookRun.objects.create(
        playbook=prev.playbook,
        user=request.user,
        status=PlaybookRun.STATUS_PENDING,
        playbook_snapshot=snapshot,
        target_server_ids=[s.id for s in servers],
        target_group_ids=[],
        options=options,
        inventory_preview=build_inventory_for_servers(servers),
    )
    start_playbook_run_async(run.id, master_password=master_password)
    return JsonResponse({"success": True, "run": _serialize_run(run)})
