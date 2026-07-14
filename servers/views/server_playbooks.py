"""Playbook / Automation API endpoints."""

from __future__ import annotations

import json
from typing import Any

from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from core_ui.activity import log_user_activity
from core_ui.decorators import require_feature
from core_ui.models import UserActivityLog
from servers.models import Playbook, PlaybookRun, ServerGroup
from servers.services.ansible_engine import (
    detect_ansible,
    generate_from_recipe,
    list_guided_recipes,
)
from servers.services.playbook_parser import parse_ansible_playbook
from servers.services.playbook_runner import (
    build_inventory_for_servers,
    normalize_tasks,
    resolve_target_servers,
    start_playbook_run_async,
)
from servers.services.playbook_templates import get_template, list_templates
from servers.views.server_helpers import _effective_master_password, _get_group_role


def _playbooks_for_user(user):
    return Playbook.objects.filter(Q(user=user) | Q(visibility=Playbook.VISIBILITY_SHARED))


def _serialize_playbook(pb: Playbook, *, include_tasks: bool = True) -> dict[str, Any]:
    data: dict[str, Any] = {
        "id": pb.id,
        "name": pb.name,
        "description": pb.description,
        "kind": pb.kind,
        "category": pb.category,
        "visibility": pb.visibility,
        "tags": pb.tags if isinstance(pb.tags, list) else [],
        "fidelity": pb.fidelity if isinstance(pb.fidelity, dict) else {},
        "task_count": pb.task_count,
        "is_template_clone": pb.is_template_clone,
        "template_slug": pb.template_slug,
        "last_run_at": pb.last_run_at.isoformat() if pb.last_run_at else None,
        "last_run_status": pb.last_run_status or "",
        "created_at": pb.created_at.isoformat() if pb.created_at else None,
        "updated_at": pb.updated_at.isoformat() if pb.updated_at else None,
        "owner_id": pb.user_id,
    }
    if include_tasks:
        data["tasks"] = pb.tasks if isinstance(pb.tasks, list) else []
        data["source_yaml"] = pb.source_yaml or ""
    return data


def _serialize_run(run: PlaybookRun, *, include_hosts: bool = True) -> dict[str, Any]:
    snapshot = run.playbook_snapshot if isinstance(run.playbook_snapshot, dict) else {}
    data: dict[str, Any] = {
        "id": run.id,
        "playbook_id": run.playbook_id,
        "status": run.status,
        "playbook_name": snapshot.get("name") or (run.playbook.name if run.playbook_id else "Playbook"),
        "target_server_ids": run.target_server_ids or [],
        "target_group_ids": run.target_group_ids or [],
        "options": run.options if isinstance(run.options, dict) else {},
        "summary": run.summary if isinstance(run.summary, dict) else {},
        "progress": run.progress if isinstance(run.progress, dict) else {},
        "inventory_preview": run.inventory_preview or "",
        "error_message": run.error_message or "",
        "cancel_requested": bool(run.cancel_requested),
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
        "created_at": run.created_at.isoformat() if run.created_at else None,
    }
    if include_hosts:
        data["host_results"] = run.host_results if isinstance(run.host_results, list) else []
        data["playbook_snapshot"] = snapshot
        data["live_log"] = (run.live_log or "")[-120_000:]
    return data


def _normalize_incoming_tasks(raw: Any) -> list[dict[str, Any]]:
    tasks = normalize_tasks(raw)
    # re-map keys for storage with snake_case
    return [
        {
            "id": t["id"],
            "command": t["command"],
            "description": t.get("description") or "",
            "continue_on_error": bool(t.get("continue_on_error")),
        }
        for t in tasks
        if not t.get("skipped_module") or t.get("command")
    ]


@login_required
@require_feature("servers")
@require_http_methods(["GET"])
def playbook_list(request):
    qs = _playbooks_for_user(request.user).order_by("-updated_at")
    category = (request.GET.get("category") or "").strip()
    kind = (request.GET.get("kind") or "").strip()
    q = (request.GET.get("q") or "").strip().lower()
    if category:
        qs = qs.filter(category=category)
    if kind:
        qs = qs.filter(kind=kind)
    items = []
    for pb in qs[:200]:
        if q:
            hay = f"{pb.name} {pb.description} {' '.join(pb.tags or [])}".lower()
            if q not in hay:
                continue
        items.append(_serialize_playbook(pb, include_tasks=False))
    return JsonResponse({"success": True, "playbooks": items, "count": len(items)})


@login_required
@require_feature("servers")
@require_http_methods(["GET"])
def playbook_detail(request, playbook_id: int):
    pb = get_object_or_404(_playbooks_for_user(request.user), id=playbook_id)
    return JsonResponse({"success": True, "playbook": _serialize_playbook(pb, include_tasks=True)})


@login_required
@require_feature("servers")
@require_http_methods(["POST"])
def playbook_create(request):
    data = json.loads(request.body or "{}")
    name = str(data.get("name") or "").strip()
    if not name:
        return JsonResponse({"success": False, "error": "Name required"}, status=400)
    tasks = _normalize_incoming_tasks(data.get("tasks") or [])
    if not tasks:
        return JsonResponse({"success": False, "error": "At least one task with a command is required"}, status=400)

    kind = str(data.get("kind") or Playbook.KIND_ANSIBLE)
    if kind not in (Playbook.KIND_RUNBOOK, Playbook.KIND_ANSIBLE):
        kind = Playbook.KIND_ANSIBLE
    category = str(data.get("category") or Playbook.CATEGORY_CUSTOM)
    valid_cats = {c[0] for c in Playbook.CATEGORY_CHOICES}
    if category not in valid_cats:
        category = Playbook.CATEGORY_CUSTOM
    visibility = str(data.get("visibility") or Playbook.VISIBILITY_PRIVATE)
    if visibility not in (Playbook.VISIBILITY_PRIVATE, Playbook.VISIBILITY_SHARED):
        visibility = Playbook.VISIBILITY_PRIVATE

    tags = data.get("tags") if isinstance(data.get("tags"), list) else []
    tags = [str(t).strip() for t in tags if str(t).strip()][:20]

    pb = Playbook.objects.create(
        user=request.user,
        name=name[:200],
        description=str(data.get("description") or "")[:4000],
        kind=kind,
        category=category,
        visibility=visibility,
        tasks=tasks,
        source_yaml=str(data.get("source_yaml") or "")[:200_000],
        tags=tags,
        fidelity=data.get("fidelity") if isinstance(data.get("fidelity"), dict) else {},
        is_template_clone=bool(data.get("is_template_clone")),
        template_slug=str(data.get("template_slug") or "")[:80],
    )
    log_user_activity(
        user=request.user,
        request=request,
        category="servers",
        action="playbook_create",
        status=UserActivityLog.STATUS_SUCCESS,
        description=f'Created playbook "{pb.name}"',
        entity_type="playbook",
        entity_id=pb.id,
        entity_name=pb.name,
    )
    return JsonResponse({"success": True, "playbook": _serialize_playbook(pb)})


@login_required
@require_feature("servers")
@require_http_methods(["POST"])
def playbook_update(request, playbook_id: int):
    pb = get_object_or_404(Playbook, id=playbook_id, user=request.user)
    data = json.loads(request.body or "{}")

    if "name" in data:
        name = str(data.get("name") or "").strip()
        if not name:
            return JsonResponse({"success": False, "error": "Name required"}, status=400)
        pb.name = name[:200]
    if "description" in data:
        pb.description = str(data.get("description") or "")[:4000]
    if "kind" in data and data["kind"] in (Playbook.KIND_RUNBOOK, Playbook.KIND_ANSIBLE):
        pb.kind = data["kind"]
    if "category" in data:
        valid_cats = {c[0] for c in Playbook.CATEGORY_CHOICES}
        if data["category"] in valid_cats:
            pb.category = data["category"]
    if "visibility" in data and data["visibility"] in (
        Playbook.VISIBILITY_PRIVATE,
        Playbook.VISIBILITY_SHARED,
    ):
        pb.visibility = data["visibility"]
    if "tasks" in data:
        tasks = _normalize_incoming_tasks(data.get("tasks") or [])
        if not tasks:
            return JsonResponse({"success": False, "error": "At least one task required"}, status=400)
        pb.tasks = tasks
    if "tags" in data and isinstance(data["tags"], list):
        pb.tags = [str(t).strip() for t in data["tags"] if str(t).strip()][:20]
    if "source_yaml" in data:
        pb.source_yaml = str(data.get("source_yaml") or "")[:200_000]
    if "fidelity" in data and isinstance(data["fidelity"], dict):
        pb.fidelity = data["fidelity"]
    pb.save()

    log_user_activity(
        user=request.user,
        request=request,
        category="servers",
        action="playbook_update",
        status=UserActivityLog.STATUS_SUCCESS,
        description=f'Updated playbook "{pb.name}"',
        entity_type="playbook",
        entity_id=pb.id,
        entity_name=pb.name,
    )
    return JsonResponse({"success": True, "playbook": _serialize_playbook(pb)})


@login_required
@require_feature("servers")
@require_http_methods(["POST"])
def playbook_delete(request, playbook_id: int):
    pb = get_object_or_404(Playbook, id=playbook_id, user=request.user)
    name = pb.name
    pid = pb.id
    pb.delete()
    log_user_activity(
        user=request.user,
        request=request,
        category="servers",
        action="playbook_delete",
        status=UserActivityLog.STATUS_SUCCESS,
        description=f'Deleted playbook "{name}"',
        entity_type="playbook",
        entity_id=pid,
        entity_name=name,
    )
    return JsonResponse({"success": True})


@login_required
@require_feature("servers")
@require_http_methods(["POST"])
def playbook_duplicate(request, playbook_id: int):
    pb = get_object_or_404(_playbooks_for_user(request.user), id=playbook_id)
    clone = Playbook.objects.create(
        user=request.user,
        name=f"{pb.name} (copy)"[:200],
        description=pb.description,
        kind=pb.kind,
        category=pb.category,
        visibility=Playbook.VISIBILITY_PRIVATE,
        tasks=list(pb.tasks or []),
        source_yaml=pb.source_yaml,
        tags=list(pb.tags or []),
        fidelity=dict(pb.fidelity or {}),
        is_template_clone=pb.is_template_clone,
        template_slug=pb.template_slug,
    )
    return JsonResponse({"success": True, "playbook": _serialize_playbook(clone)})


@login_required
@require_feature("servers")
@require_http_methods(["POST"])
def playbook_import(request):
    data = json.loads(request.body or "{}")
    content = str(data.get("content") or data.get("yaml") or "")
    filename = str(data.get("filename") or "playbook.yml")
    save = bool(data.get("save", True))
    try:
        parsed = parse_ansible_playbook(content, filename)
    except ValueError as exc:
        return JsonResponse({"success": False, "error": str(exc)}, status=400)

    if not save:
        return JsonResponse({"success": True, "parsed": parsed})

    pb = Playbook.objects.create(
        user=request.user,
        name=str(parsed["name"])[:200],
        description=str(parsed.get("description") or "")[:4000],
        kind=parsed.get("kind") or Playbook.KIND_ANSIBLE,
        category=Playbook.CATEGORY_CUSTOM,
        visibility=Playbook.VISIBILITY_PRIVATE,
        tasks=parsed.get("tasks") or [],
        source_yaml=parsed.get("source_yaml") or content,
        tags=parsed.get("tags") or ["imported"],
        fidelity=parsed.get("fidelity") or {},
    )
    log_user_activity(
        user=request.user,
        request=request,
        category="servers",
        action="playbook_import",
        status=UserActivityLog.STATUS_SUCCESS,
        description=f'Imported playbook "{pb.name}"',
        entity_type="playbook",
        entity_id=pb.id,
        entity_name=pb.name,
        metadata={"fidelity": pb.fidelity},
    )
    return JsonResponse({"success": True, "playbook": _serialize_playbook(pb), "parsed": parsed})


@login_required
@require_feature("servers")
@require_http_methods(["GET"])
def playbook_ansible_status(request):
    status = detect_ansible()
    return JsonResponse({"success": True, "ansible": status})


@login_required
@require_feature("servers")
@require_http_methods(["GET"])
def playbook_guided_recipes(request):
    return JsonResponse({"success": True, "recipes": list_guided_recipes()})


@login_required
@require_feature("servers")
@require_http_methods(["POST"])
def playbook_guided_generate(request):
    data = json.loads(request.body or "{}")
    slug = str(data.get("slug") or data.get("recipe") or "").strip()
    params = data.get("params") if isinstance(data.get("params"), dict) else {}
    save = bool(data.get("save", True))
    try:
        generated = generate_from_recipe(slug, params)
    except ValueError as exc:
        return JsonResponse({"success": False, "error": str(exc)}, status=400)

    if not save:
        return JsonResponse({"success": True, "playbook": generated, "preview": True})

    pb = Playbook.objects.create(
        user=request.user,
        name=str(generated["name"])[:200],
        description=str(generated.get("description") or "")[:4000],
        kind=Playbook.KIND_ANSIBLE,
        category=generated.get("category") or Playbook.CATEGORY_CUSTOM,
        visibility=Playbook.VISIBILITY_PRIVATE,
        tasks=generated.get("tasks") or [],
        source_yaml=generated.get("source_yaml") or "",
        tags=list(generated.get("tags") or []),
        fidelity=generated.get("fidelity") or {},
        is_template_clone=True,
        template_slug=f"guided:{slug}",
    )
    return JsonResponse({"success": True, "playbook": _serialize_playbook(pb)})


@login_required
@require_feature("servers")
@require_http_methods(["GET"])
def playbook_templates(request):
    return JsonResponse({"success": True, "templates": list_templates()})


@login_required
@require_feature("servers")
@require_http_methods(["POST"])
def playbook_template_install(request, slug: str):
    tmpl = get_template(slug)
    if not tmpl:
        return JsonResponse({"success": False, "error": "Template not found"}, status=404)
    pb = Playbook.objects.create(
        user=request.user,
        name=tmpl["name"][:200],
        description=tmpl.get("description") or "",
        kind=tmpl.get("kind") or Playbook.KIND_ANSIBLE,
        category=tmpl.get("category") or Playbook.CATEGORY_CUSTOM,
        visibility=Playbook.VISIBILITY_PRIVATE,
        tasks=tmpl.get("tasks") or [],
        source_yaml=str(tmpl.get("source_yaml") or ""),
        tags=list(tmpl.get("tags") or []),
        is_template_clone=True,
        template_slug=slug,
        fidelity=tmpl.get("fidelity") if isinstance(tmpl.get("fidelity"), dict) else {"engine": "ansible"},
    )
    return JsonResponse({"success": True, "playbook": _serialize_playbook(pb)})


@login_required
@require_feature("servers")
@require_http_methods(["POST"])
def playbook_inventory_preview(request):
    data = json.loads(request.body or "{}")
    server_ids = [int(x) for x in (data.get("server_ids") or []) if str(x).isdigit() or isinstance(x, int)]
    group_ids = [int(x) for x in (data.get("group_ids") or []) if str(x).isdigit() or isinstance(x, int)]
    servers = resolve_target_servers(request.user, server_ids=server_ids, group_ids=group_ids)
    inventory = build_inventory_for_servers(servers)
    return JsonResponse(
        {
            "success": True,
            "inventory": inventory,
            "hosts": [
                {
                    "id": s.id,
                    "name": s.name,
                    "host": s.host,
                    "port": s.port,
                    "username": s.username,
                    "group_id": s.group_id,
                    "detected_os": getattr(s, "detected_os", "") or "",
                }
                for s in servers
            ],
            "count": len(servers),
        }
    )


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
