"""Playbook / Automation API endpoints."""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import PurePosixPath

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from core_ui.activity import log_user_activity
from core_ui.decorators import require_feature
from core_ui.models import UserActivityLog
from servers.models import BackgroundWorkerState, Playbook, PlaybookRevision
from servers.playbooks.dispatch import PLAYBOOK_EXECUTION_WORKER_KIND
from servers.services.ansible_engine import (
    detect_ansible,
    generate_from_recipe,
    list_guided_recipes,
)
from servers.services.ansible_validator_client import validator_runtime_available, validator_socket_path
from servers.services.playbook_compatibility_analysis import analyze_playbook_compatibility
from servers.services.playbook_parser import parse_ansible_playbook
from servers.services.playbook_templates import get_template, list_templates
from servers.services.playbooks.access import capabilities_for
from servers.services.playbooks.audit import record_playbook_event
from servers.services.playbooks.bundle_archive import BundleValidationError, normalize_bundle_path
from servers.services.playbooks.legacy_api_safety import (
    LegacySourceSafetyError,
    inspect_legacy_source,
    sanitize_legacy_preview,
    validate_legacy_playbook_egress,
    validate_legacy_revision_egress,
)
from servers.services.playbooks.revisions import (
    ensure_playbook_workspace,
    initialize_created_playbook,
    initialize_forked_playbook,
    sync_legacy_content_save,
)
from servers.services.playbooks.sharing import sync_legacy_visibility_grant
from servers.views.playbook_workspace_helpers import get_playbook_for_action
from servers.views.server_playbook_serializers import (
    _normalize_incoming_tasks,
    _playbooks_for_user,
    _serialize_playbook,
)


@login_required
@require_feature("automation")
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
        items.append(_serialize_playbook(pb, include_tasks=False, viewer=request.user))
    return JsonResponse({"success": True, "playbooks": items, "count": len(items)})


@login_required
@require_feature("automation")
@require_http_methods(["GET"])
def playbook_detail(request, playbook_id: int):
    pb = get_object_or_404(_playbooks_for_user(request.user), id=playbook_id)
    capabilities = capabilities_for(pb, request.user)
    if not capabilities.is_owner:
        try:
            validate_legacy_playbook_egress(pb)
        except BundleValidationError as exc:
            return JsonResponse(
                {
                    "success": False,
                    "error": "Published playbook content failed safety validation",
                    "code": exc.code,
                },
                status=422,
            )
    return JsonResponse({"success": True, "playbook": _serialize_playbook(pb, include_tasks=True, viewer=request.user)})


@login_required
@require_feature("automation")
@require_http_methods(["POST"])
def playbook_create(request):
    data = json.loads(request.body or "{}")
    name = str(data.get("name") or "").strip()
    if not name:
        return JsonResponse({"success": False, "error": "Name required"}, status=400)
    tasks = _normalize_incoming_tasks(data.get("tasks") or [])
    source_yaml = str(data.get("source_yaml") or "")
    if not tasks and not source_yaml.strip():
        return JsonResponse(
            {"success": False, "error": "Ansible YAML or at least one runbook task is required"},
            status=400,
        )

    kind = str(data.get("kind") or Playbook.KIND_ANSIBLE)
    if kind not in (Playbook.KIND_RUNBOOK, Playbook.KIND_ANSIBLE):
        kind = Playbook.KIND_ANSIBLE
    category = str(data.get("category") or Playbook.CATEGORY_CUSTOM)
    valid_cats = {c[0] for c in Playbook.CATEGORY_CHOICES}
    if category not in valid_cats:
        category = Playbook.CATEGORY_CUSTOM
    visibility = Playbook.VISIBILITY_PRIVATE

    tags = data.get("tags") if isinstance(data.get("tags"), list) else []
    tags = [str(t).strip() for t in tags if str(t).strip()][:20]

    try:
        safety = inspect_legacy_source(source_yaml) if source_yaml else None
    except LegacySourceSafetyError as exc:
        return _source_error(exc)
    compatibility = safety.compatibility if safety else {}
    pb = Playbook.objects.create(
        user=request.user,
        name=name[:200],
        description=str(data.get("description") or "")[:4000],
        kind=kind,
        category=category,
        visibility=visibility,
        tasks=tasks,
        source_yaml=source_yaml,
        compatibility=compatibility,
        tags=tags,
        fidelity=data.get("fidelity") if isinstance(data.get("fidelity"), dict) else {},
        is_template_clone=bool(data.get("is_template_clone")),
        template_slug=str(data.get("template_slug") or "")[:80],
    )
    initialize_created_playbook(
        pb,
        actor=request.user,
        origin_type=PlaybookRevision.ORIGIN_MANUAL,
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
    return JsonResponse({"success": True, "playbook": _serialize_playbook(pb, viewer=request.user)})


@dataclass
class _PlaybookUpdateState:
    content_changed: bool = False
    visibility_changed: bool = False


def _apply_update_metadata(pb: Playbook, data: dict, state: _PlaybookUpdateState) -> JsonResponse | None:
    if "name" in data:
        name = str(data.get("name") or "").strip()
        if not name:
            return JsonResponse({"success": False, "error": "Name required"}, status=400)
        pb.name = name[:200]
    if "description" in data:
        pb.description = str(data.get("description") or "")[:4000]
    if "kind" in data and data["kind"] in (Playbook.KIND_RUNBOOK, Playbook.KIND_ANSIBLE):
        state.content_changed = state.content_changed or pb.kind != data["kind"]
        pb.kind = data["kind"]
    if "category" in data:
        valid_categories = {choice[0] for choice in Playbook.CATEGORY_CHOICES}
        if data["category"] in valid_categories:
            pb.category = data["category"]
    if "visibility" in data and data["visibility"] in (
        Playbook.VISIBILITY_PRIVATE,
        Playbook.VISIBILITY_SHARED,
    ):
        if pb.visibility != Playbook.VISIBILITY_SHARED and data["visibility"] == Playbook.VISIBILITY_SHARED:
            return JsonResponse(
                {
                    "success": False,
                    "error": "New workspace-wide playbook sharing is not allowed; use explicit user or group shares",
                    "code": "playbook_workspace_share_disabled",
                },
                status=400,
            )
        state.visibility_changed = pb.visibility != data["visibility"]
        pb.visibility = data["visibility"]
    return None


def _apply_update_content(pb: Playbook, draft, data: dict, state: _PlaybookUpdateState) -> JsonResponse | None:
    if draft.asset_bundle_id and any(key in data for key in ("kind", "tasks", "source_yaml")):
        return JsonResponse(
            {
                "success": False,
                "error": "Bundled playbook content must be edited through the draft file API",
                "code": "playbook_draft_file_api_required",
            },
            status=409,
        )
    if "tasks" in data:
        tasks = _normalize_incoming_tasks(data.get("tasks") or [])
        state.content_changed = state.content_changed or tasks != pb.tasks
        pb.tasks = tasks
    if "tags" in data and isinstance(data["tags"], list):
        pb.tags = [str(tag).strip() for tag in data["tags"] if str(tag).strip()][:20]
    if "source_yaml" in data:
        next_source = str(data.get("source_yaml") or "")
        try:
            source_safety = inspect_legacy_source(next_source) if next_source else None
        except LegacySourceSafetyError as exc:
            return _source_error(exc)
        source_changed = next_source != pb.source_yaml
        state.content_changed = state.content_changed or source_changed
        pb.source_yaml = next_source
        if source_changed:
            pb.compatibility = source_safety.compatibility if source_safety else {}
            pb.active_compatibility_revision = None
    if not (pb.source_yaml or "").strip() and not _normalize_incoming_tasks(pb.tasks or []):
        return JsonResponse(
            {"success": False, "error": "Ansible YAML or at least one runbook task is required"},
            status=400,
        )
    if "fidelity" in data and isinstance(data["fidelity"], dict):
        pb.fidelity = data["fidelity"]
    return None


@login_required
@require_feature("automation")
@require_http_methods(["POST"])
@transaction.atomic
def playbook_update(request, playbook_id: int):
    try:
        visible = get_playbook_for_action(request.user, playbook_id, "edit")
    except PermissionDenied as exc:
        return JsonResponse(
            {"success": False, "error": str(exc), "code": "playbook_forbidden"},
            status=403,
        )
    pb = Playbook.objects.select_for_update().get(pk=visible.pk)
    try:
        _revision, draft = ensure_playbook_workspace(pb, actor=request.user)
    except BundleValidationError as exc:
        return JsonResponse(
            {"success": False, "error": "Playbook content failed safety validation", "code": exc.code},
            status=exc.status_code,
        )
    data = json.loads(request.body or "{}")
    state = _PlaybookUpdateState()
    invalid = _apply_update_metadata(pb, data, state) or _apply_update_content(pb, draft, data, state)
    if invalid:
        return invalid
    pb.save()
    if state.content_changed:
        sync_legacy_content_save(pb, actor=request.user)
        pb.refresh_from_db()
    if state.visibility_changed:
        sync_legacy_visibility_grant(pb, actor=request.user)

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
    return JsonResponse({"success": True, "playbook": _serialize_playbook(pb, viewer=request.user)})


@login_required
@require_feature("automation")
@require_http_methods(["POST"])
def playbook_delete(request, playbook_id: int):
    pb = get_object_or_404(Playbook, id=playbook_id, user=request.user)
    name = pb.name
    pid = pb.id
    record_playbook_event(
        playbook=pb,
        actor=request.user,
        event_type="playbook_archived",
        metadata={"name": name},
    )
    pb.is_archived = True
    pb.visibility = Playbook.VISIBILITY_PRIVATE
    pb.save(update_fields=["is_archived", "visibility", "updated_at"])
    pb.grants.filter(revoked_at__isnull=True).update(revoked_at=timezone.now())
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
@require_feature("automation")
@require_http_methods(["POST"])
def playbook_restore(request, playbook_id: int):
    pb = get_object_or_404(
        Playbook,
        id=playbook_id,
        user=request.user,
        is_archived=True,
    )
    pb.is_archived = False
    pb.save(update_fields=["is_archived", "updated_at"])
    record_playbook_event(playbook=pb, actor=request.user, event_type="playbook_restored")
    return JsonResponse({"success": True, "playbook": _serialize_playbook(pb, viewer=request.user)})


@login_required
@require_feature("automation")
@require_http_methods(["POST"])
def playbook_duplicate(request, playbook_id: int):
    pb = get_object_or_404(_playbooks_for_user(request.user), id=playbook_id)
    if not capabilities_for(pb, request.user).can_export:
        return JsonResponse({"success": False, "error": "Playbook export capability required"}, status=403)
    published = pb.published_revision
    try:
        if published is None:
            published, _draft = ensure_playbook_workspace(pb, actor=request.user)
        validate_legacy_revision_egress(published)
    except BundleValidationError as exc:
        return JsonResponse(
            {
                "success": False,
                "error": "Published playbook content failed safety validation",
                "code": exc.code,
            },
            status=422,
        )
    clone = Playbook.objects.create(
        user=request.user,
        name=f"{pb.name} (copy)"[:200],
        description=pb.description,
        kind=pb.kind,
        category=pb.category,
        visibility=Playbook.VISIBILITY_PRIVATE,
        tasks=list((published.tasks if published else pb.tasks) or []),
        source_yaml=(published.source_yaml if published else pb.source_yaml),
        tags=list(pb.tags or []),
        fidelity=dict(pb.fidelity or {}),
        compatibility=dict(pb.compatibility or {}),
        is_template_clone=pb.is_template_clone,
        template_slug=pb.template_slug,
        forked_from_revision=published,
    )
    initialize_forked_playbook(clone, published, actor=request.user)
    return JsonResponse({"success": True, "playbook": _serialize_playbook(clone, viewer=request.user)})


@login_required
@require_feature("automation")
@require_http_methods(["POST"])
@transaction.atomic
def playbook_import(request):
    data = json.loads(request.body or "{}")
    content = str(data.get("content") or data.get("yaml") or "")
    try:
        filename = _normalize_raw_import_path(data.get("path") or data.get("filename") or "playbook.yml")
    except LegacySourceSafetyError as exc:
        return _source_error(exc)
    save = bool(data.get("save", True))
    try:
        safety = inspect_legacy_source(content, path=filename)
        parsed = parse_ansible_playbook(content, filename)
    except LegacySourceSafetyError as exc:
        if not save and exc.code == "secret_material_detected":
            try:
                parse_ansible_playbook(content, filename)
            except ValueError as parse_exc:
                return JsonResponse({"success": False, "error": str(parse_exc)}, status=400)
            content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
            compatibility = analyze_playbook_compatibility(content)
            findings = _redacted_source_findings(exc.details)
            preview = _raw_import_preview(
                source_yaml=content,
                content_hash=content_hash,
                compatibility=sanitize_legacy_preview(compatibility),
                secret_findings=findings,
                entrypoint=filename,
            )
            # Parsed labels/tags may themselves contain the detected token.
            # A blocked preview exposes structure only, never source-derived text.
            return JsonResponse({"success": True, "preview": True, "parsed": {"tasks": []}, **preview})
        return _source_error(exc)
    except ValueError as exc:
        return JsonResponse({"success": False, "error": str(exc)}, status=400)

    preview = _raw_import_preview(
        source_yaml=safety.source_yaml,
        content_hash=safety.content_hash,
        compatibility=safety.compatibility,
        secret_findings=list(safety.secret_findings),
        entrypoint=filename,
    )
    if not save:
        return JsonResponse({"success": True, "preview": True, "parsed": parsed, **preview})

    expected_content_hash = str(data.get("expected_content_hash") or "").strip().casefold()
    if not expected_content_hash:
        return JsonResponse(
            {
                "success": False,
                "error": "Preview the exact YAML before importing it",
                "code": "playbook_import_preview_required",
            },
            status=409,
        )
    if expected_content_hash != safety.content_hash:
        return JsonResponse(
            {
                "success": False,
                "error": "The YAML changed after preview; preview it again",
                "code": "playbook_import_source_changed",
                "details": {
                    "expected_content_hash": expected_content_hash,
                    "current_content_hash": safety.content_hash,
                },
            },
            status=409,
        )

    compatibility = safety.compatibility
    pb = Playbook.objects.create(
        user=request.user,
        name=str(parsed["name"])[:200],
        description=str(parsed.get("description") or "")[:4000],
        kind=parsed.get("kind") or Playbook.KIND_ANSIBLE,
        category=Playbook.CATEGORY_CUSTOM,
        visibility=Playbook.VISIBILITY_PRIVATE,
        tasks=parsed.get("tasks") or [],
        source_yaml=safety.source_yaml,
        tags=parsed.get("tags") or ["imported"],
        fidelity=parsed.get("fidelity") or {},
        compatibility=compatibility,
    )
    initialize_created_playbook(pb, actor=request.user, origin_type=PlaybookRevision.ORIGIN_IMPORTED)
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
    return JsonResponse(
        {
            "success": True,
            "playbook": _serialize_playbook(pb, viewer=request.user),
            "parsed": parsed,
            "content_hash": safety.content_hash,
            "entrypoint": filename,
        }
    )


def _normalize_raw_import_path(raw_path) -> str:
    candidate = str(raw_path or "playbook.yml").strip() or "playbook.yml"
    try:
        normalized = normalize_bundle_path(candidate)
    except BundleValidationError as exc:
        raise LegacySourceSafetyError(
            "YAML filename contains an unsafe path",
            code="playbook_import_path_invalid",
            status_code=400,
            details={"reason": exc.code},
        ) from exc
    path = PurePosixPath(normalized)
    suffix = path.suffix.casefold()
    if suffix not in {".yml", ".yaml"}:
        raise LegacySourceSafetyError(
            "YAML filename must end with .yml or .yaml",
            code="playbook_import_path_invalid",
            status_code=400,
            details={"allowed_extensions": [".yml", ".yaml"]},
        )
    return path.with_suffix(suffix).as_posix()


def _raw_import_preview(
    *,
    source_yaml: str,
    content_hash: str,
    compatibility: dict,
    secret_findings: list[dict],
    entrypoint: str,
) -> dict:
    compatibility = compatibility if isinstance(compatibility, dict) else {}
    dependencies = compatibility.get("dependencies")
    if not isinstance(dependencies, dict):
        dependencies = {"roles": [], "collections": [], "assets": []}
    size_bytes = len(source_yaml.encode("utf-8"))
    findings = list(secret_findings)
    return {
        "content_hash": content_hash,
        "tree": {
            "entrypoint": entrypoint,
            "files": [
                {
                    "path": entrypoint,
                    "size_bytes": size_bytes,
                    "sha256": content_hash,
                    "is_text": True,
                    "editable": True,
                    "is_entrypoint": True,
                }
            ],
        },
        "entrypoint": entrypoint,
        "dependencies": {
            "roles": list(dependencies.get("roles") or []),
            "collections": list(dependencies.get("collections") or []),
            "assets": list(dependencies.get("assets") or []),
        },
        "compatibility": compatibility,
        "secret_findings": findings,
        "safe_to_commit": not findings,
    }


def _redacted_source_findings(details: dict) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    for item in details.get("findings") or []:
        if isinstance(item, dict):
            findings.append(
                {"path": str(item.get("path") or "playbook.yml"), "kind": str(item.get("kind") or "secret")}
            )
    for item in details.get("issues") or []:
        if isinstance(item, dict):
            findings.append(
                {
                    "path": str(item.get("path") or "playbook"),
                    "kind": str(item.get("code") or "literal_secret"),
                }
            )
    unique = {(item["path"], item["kind"]): item for item in findings}
    return [unique[key] for key in sorted(unique)]


def _source_error(exc: LegacySourceSafetyError) -> JsonResponse:
    payload = {"success": False, "error": str(exc), "code": exc.code}
    if exc.details:
        payload["details"] = exc.details
    return JsonResponse(payload, status=exc.status_code)


@login_required
@require_feature("automation")
@require_http_methods(["GET"])
def playbook_ansible_status(request):
    if validator_socket_path():
        available = validator_runtime_available()
        status = {
            "available": available,
            "method": "isolated-worker" if available else "none",
            "binary": "",
            "version": "image-managed",
            "image": os.environ.get("WEBTERM_ANSIBLE_IMAGE", "webterm-ansible:latest"),
            "image_ready": available,
            "message": (
                "Isolated Ansible validation and worker runtime are ready"
                if available
                else "Isolated Ansible validator is unavailable"
            ),
        }
    else:
        status = detect_ansible()
    validation_available = bool(status.get("available"))
    worker_ready = BackgroundWorkerState.objects.filter(
        worker_kind=PLAYBOOK_EXECUTION_WORKER_KIND,
        status=BackgroundWorkerState.STATUS_RUNNING,
        lease_expires_at__gt=timezone.now(),
    ).exists()
    status["validation_available"] = validation_available
    status["worker_ready"] = worker_ready
    status["available"] = validation_available and worker_ready
    if validation_available and not worker_ready:
        status["message"] = "Ansible validation is ready; execution worker is not heartbeating"
    return JsonResponse({"success": True, "ansible": status})


@login_required
@require_feature("automation")
@require_http_methods(["GET"])
def playbook_guided_recipes(request):
    return JsonResponse({"success": True, "recipes": list_guided_recipes()})


@login_required
@require_feature("automation")
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

    try:
        source_safety = inspect_legacy_source(generated.get("source_yaml") or "")
    except LegacySourceSafetyError as exc:
        return _source_error(exc)

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
        source_yaml=source_safety.source_yaml,
        tags=list(generated.get("tags") or []),
        fidelity=generated.get("fidelity") or {},
        is_template_clone=True,
        template_slug=f"guided:{slug}",
    )
    initialize_created_playbook(pb, actor=request.user, origin_type=PlaybookRevision.ORIGIN_GUIDED)
    return JsonResponse({"success": True, "playbook": _serialize_playbook(pb, viewer=request.user)})


@login_required
@require_feature("automation")
@require_http_methods(["GET"])
def playbook_templates(request):
    return JsonResponse({"success": True, "templates": list_templates()})


@login_required
@require_feature("automation")
@require_http_methods(["POST"])
def playbook_template_install(request, slug: str):
    tmpl = get_template(slug)
    if not tmpl:
        return JsonResponse({"success": False, "error": "Template not found"}, status=404)
    template_source = str(tmpl.get("source_yaml") or "")
    if template_source:
        try:
            template_source = inspect_legacy_source(template_source).source_yaml
        except LegacySourceSafetyError as exc:
            return _source_error(exc)
    pb = Playbook.objects.create(
        user=request.user,
        name=tmpl["name"][:200],
        description=tmpl.get("description") or "",
        kind=tmpl.get("kind") or Playbook.KIND_ANSIBLE,
        category=tmpl.get("category") or Playbook.CATEGORY_CUSTOM,
        visibility=Playbook.VISIBILITY_PRIVATE,
        tasks=tmpl.get("tasks") or [],
        source_yaml=template_source,
        tags=list(tmpl.get("tags") or []),
        is_template_clone=True,
        template_slug=slug,
        fidelity=tmpl.get("fidelity") if isinstance(tmpl.get("fidelity"), dict) else {"engine": "ansible"},
    )
    initialize_created_playbook(pb, actor=request.user, origin_type=PlaybookRevision.ORIGIN_TEMPLATE)
    return JsonResponse({"success": True, "playbook": _serialize_playbook(pb, viewer=request.user)})


# Run lifecycle views live in server_playbook_run_views (split for size limits);
# re-exported so servers/urls.py can keep addressing them here.
from servers.views.server_playbook_inventory_views import playbook_inventory_preview  # noqa: E402, F401
from servers.views.server_playbook_run_views import (  # noqa: E402, F401
    playbook_run,
    playbook_run_cancel,
    playbook_run_detail,
    playbook_run_list,
    playbook_run_rerun_failed,
)
