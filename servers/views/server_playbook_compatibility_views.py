"""Compatibility analysis, guarded AI adaptation, and revision APIs."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_http_methods

from core_ui.ai_model_policy import operational_provider_binding
from core_ui.decorators import require_feature
from servers.services.playbook_compatibility_ai import (
    PlaybookAdaptationError,
    adapt_playbook_with_ai,
    adapt_yaml_fragment_with_ai,
    validate_yaml_fragment_safety,
)
from servers.services.playbook_compatibility_analysis import (
    analyze_playbook_compatibility,
    merge_syntax_check,
)
from servers.services.playbook_compatibility_inventory import normalize_inventory_bindings
from servers.services.playbook_compatibility_validation import validate_playbook_syntax
from servers.services.playbook_runner import resolve_target_servers
from servers.services.playbooks.access import capabilities_for, playbooks_visible_to
from servers.services.playbooks.bundle_archive import BundleValidationError, calculate_bundle_content_hash
from servers.services.playbooks.bundle_storage import BundleStorageError
from servers.services.playbooks.draft_files import (
    get_draft_text_file,
    is_editable_draft_yaml_path,
)
from servers.services.playbooks.revisions import DraftConflict, ensure_playbook_workspace
from servers.services.playbooks.serialization import serialize_draft
from servers.views.playbook_compatibility_apply_helpers import (
    CompatibilityApplyEvaluationError,
    CompatibilityApplyInputError,
    compatibility_failure_message,
    compatibility_revision_payload,
    evaluate_compatibility_apply,
    expectation_is_stale,
    parse_base_expectation,
    persist_compatibility_apply,
)
from servers.views.playbook_workspace_helpers import get_playbook_for_action
from servers.views.server_playbook_serializers import _playbooks_for_user


def _json_body(request) -> dict[str, Any]:
    try:
        parsed = json.loads(request.body or "{}")
    except (TypeError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _binding_context(
    user, raw_bindings: Any
) -> tuple[dict[str, dict[str, list[int]]], dict[str, list[int]], list[Any]]:
    normalized = normalize_inventory_bindings(raw_bindings)
    resolved: dict[str, list[int]] = {}
    servers_by_id: dict[int, Any] = {}
    for selector, binding in normalized.items():
        servers = resolve_target_servers(
            user,
            server_ids=binding["server_ids"],
            group_ids=binding["group_ids"],
        )
        resolved[selector] = sorted({server.id for server in servers})
        servers_by_id.update({server.id: server for server in servers})
    return normalized, resolved, list(servers_by_id.values())


def _source_from_payload(data: dict[str, Any]) -> str:
    return str(data.get("source_yaml") or "").strip()


def _validate_source_payload(source: str) -> JsonResponse | None:
    if not source:
        return JsonResponse({"success": False, "error": "Ansible YAML is required"}, status=400)
    try:
        source_size = len(source.encode("utf-8"))
    except UnicodeEncodeError:
        return JsonResponse(
            {"success": False, "error": "Ansible YAML must be valid UTF-8", "code": "playbook_source_encoding"},
            status=400,
        )
    if source_size > 200_000:
        return JsonResponse({"success": False, "error": "Playbook YAML is too large"}, status=413)
    return None


def _editable_draft_base(playbook, *, actor, path: str = ""):
    _revision, draft = ensure_playbook_workspace(playbook, actor=actor)
    draft = type(draft).objects.select_related("asset_bundle", "base_revision").get(pk=draft.pk)
    snapshot = get_draft_text_file(draft, path=path)
    if not is_editable_draft_yaml_path(snapshot.path):
        raise BundleValidationError(
            "This project file is read-only",
            code="draft_file_read_only",
            status_code=422,
        )
    return (
        draft,
        snapshot,
        {
            "path": snapshot.path,
            "content_hash": snapshot.sha256,
            "draft_version": draft.version,
            "version": draft.version,
            "bundle_hash": draft.bundle_hash
            or calculate_bundle_content_hash({snapshot.path: snapshot.content.encode("utf-8")}),
            "base_revision_id": draft.base_revision_id,
        },
    )


def _stale_response(*, current: dict[str, Any]) -> JsonResponse:
    return JsonResponse(
        {
            "success": False,
            "error": "The draft changed after compatibility analysis; analyze it again",
            "code": "playbook_compatibility_stale",
            "details": {"current": current},
        },
        status=409,
    )


@login_required
@require_feature("automation")
@require_http_methods(["POST"])
def playbook_source_compatibility_analyze(request):
    data = _json_body(request)
    source = _source_from_payload(data)
    invalid = _validate_source_payload(source)
    if invalid:
        return invalid
    bindings, _resolved, target_servers = _binding_context(request.user, data.get("inventory_bindings"))
    report = analyze_playbook_compatibility(source, bindings=bindings, target_servers=target_servers)
    if bool(data.get("syntax_check", True)) and not any(
        item.get("severity") == "error" for item in report.get("issues") or []
    ):
        report = merge_syntax_check(
            report,
            validate_playbook_syntax(source, allow_dependency_setup=False),
        )
    return JsonResponse({"success": True, "report": report})


@login_required
@require_feature("automation")
@require_http_methods(["POST"])
def playbook_source_compatibility_adapt(request):
    data = _json_body(request)
    source = _source_from_payload(data)
    invalid = _validate_source_payload(source)
    if invalid:
        return invalid
    bindings, _resolved, target_servers = _binding_context(request.user, data.get("inventory_bindings"))
    try:
        proposal = adapt_playbook_with_ai(
            source,
            bindings=bindings,
            target_servers=target_servers,
            user_instruction=str(data.get("instruction") or ""),
            user=request.user,
            provider_binding=operational_provider_binding(request.user, data.get("provider_binding")),
        )
    except PlaybookAdaptationError as exc:
        return JsonResponse({"success": False, "error": str(exc)}, status=400)
    return JsonResponse({"success": True, "proposal": proposal})


@login_required
@require_feature("automation")
@require_http_methods(["POST"])
def playbook_compatibility_analyze(request, playbook_id: int):
    playbook = get_object_or_404(playbooks_visible_to(request.user), id=playbook_id)
    capabilities = capabilities_for(playbook, request.user)
    if not capabilities.can_validate:
        return JsonResponse({"success": False, "error": "Playbook validation capability required"}, status=403)
    data = _json_body(request)
    bindings, _resolved, binding_servers = _binding_context(request.user, data.get("inventory_bindings"))
    explicit_servers = resolve_target_servers(
        request.user,
        server_ids=[int(item) for item in data.get("server_ids") or [] if str(item).isdigit()],
        group_ids=[int(item) for item in data.get("group_ids") or [] if str(item).isdigit()],
    )
    target_servers = list({server.id: server for server in [*binding_servers, *explicit_servers]}.values())
    base = None
    snapshot = None
    if capabilities.can_edit:
        try:
            _draft, snapshot, base = _editable_draft_base(
                playbook,
                actor=request.user,
                path=str(data.get("path") or ""),
            )
        except (BundleValidationError, BundleStorageError) as exc:
            return JsonResponse(
                {"success": False, "error": str(exc), "code": getattr(exc, "code", "bundle_unavailable")},
                status=getattr(exc, "status_code", 409),
            )
        source = snapshot.content
    else:
        source = playbook.published_revision.source_yaml if playbook.published_revision_id else playbook.source_yaml
        source = str(source or "")
        base = {
            "path": "playbook.yml",
            "content_hash": hashlib.sha256(source.encode("utf-8")).hexdigest(),
            "draft_version": None,
            "version": None,
            "bundle_hash": str(getattr(playbook.published_revision, "bundle_hash", "") or ""),
            "base_revision_id": playbook.published_revision_id,
        }
    if not source:
        return JsonResponse({"success": False, "error": "Playbook has no imported Ansible YAML"}, status=400)
    if len(source.encode("utf-8")) > 200_000:
        return JsonResponse({"success": False, "error": "Playbook YAML is too large"}, status=413)
    if snapshot is not None and not snapshot.is_entrypoint:
        try:
            validate_yaml_fragment_safety(source, path=snapshot.path)
        except PlaybookAdaptationError as exc:
            return JsonResponse(
                {"success": False, "error": str(exc), "code": "playbook_fragment_invalid"},
                status=422,
            )
        report = {
            "status": "ready",
            "ready": True,
            "issues": [],
            "syntax_check": {"status": "passed", "passed": True, "method": "safe-yaml"},
        }
    else:
        report = analyze_playbook_compatibility(source, bindings=bindings, target_servers=target_servers)
        if bool(data.get("syntax_check", True)) and not any(
            item.get("severity") == "error" for item in report.get("issues") or []
        ):
            report = merge_syntax_check(
                report,
                validate_playbook_syntax(source, allow_dependency_setup=False),
            )
    return JsonResponse({"success": True, "report": report, "base": base})


@login_required
@require_feature("automation")
@require_http_methods(["POST"])
def playbook_compatibility_adapt(request, playbook_id: int):
    try:
        playbook = get_playbook_for_action(request.user, playbook_id, "edit")
    except PermissionDenied as exc:
        return JsonResponse({"success": False, "error": str(exc), "code": "playbook_forbidden"}, status=403)
    data = _json_body(request)
    bindings, _resolved, target_servers = _binding_context(request.user, data.get("inventory_bindings"))
    try:
        _draft, snapshot, base = _editable_draft_base(
            playbook,
            actor=request.user,
            path=str(data.get("path") or ""),
        )
    except (BundleValidationError, BundleStorageError) as exc:
        return JsonResponse(
            {"success": False, "error": str(exc), "code": getattr(exc, "code", "bundle_unavailable")},
            status=getattr(exc, "status_code", 409),
        )
    source = snapshot.content
    if not source:
        return JsonResponse({"success": False, "error": "Playbook has no imported Ansible YAML"}, status=400)
    try:
        common = {
            "user_instruction": str(data.get("instruction") or ""),
            "user": request.user,
            "provider_binding": operational_provider_binding(request.user, data.get("provider_binding")),
        }
        if snapshot.is_entrypoint:
            proposal = adapt_playbook_with_ai(
                source,
                bindings=bindings,
                target_servers=target_servers,
                **common,
            )
        else:
            proposal = adapt_yaml_fragment_with_ai(source, path=snapshot.path, **common)
    except PlaybookAdaptationError as exc:
        return JsonResponse({"success": False, "error": str(exc)}, status=400)
    return JsonResponse({"success": True, "proposal": proposal, "base": base})


@login_required
@require_feature("automation")
@require_http_methods(["POST"])
def playbook_compatibility_apply(request, playbook_id: int):
    try:
        playbook = get_playbook_for_action(request.user, playbook_id, "edit")
    except PermissionDenied as exc:
        return JsonResponse({"success": False, "error": str(exc), "code": "playbook_forbidden"}, status=403)
    data = _json_body(request)
    try:
        expectation = parse_base_expectation(data)
    except CompatibilityApplyInputError as exc:
        return JsonResponse(
            {
                "success": False,
                "error": str(exc),
                "code": "playbook_compatibility_base_required",
            },
            status=400,
        )
    try:
        draft, snapshot, current_base = _editable_draft_base(
            playbook,
            actor=request.user,
            path=expectation.path,
        )
    except (BundleValidationError, BundleStorageError) as exc:
        return JsonResponse(
            {"success": False, "error": str(exc), "code": getattr(exc, "code", "bundle_unavailable")},
            status=getattr(exc, "status_code", 409),
        )
    if expectation_is_stale(expectation, current=current_base, selected_path=snapshot.path):
        return _stale_response(current=current_base)
    source = snapshot.content
    adapted_yaml = str(data.get("adapted_yaml") or "")
    if not source or not adapted_yaml:
        return JsonResponse({"success": False, "error": "source and adapted YAML are required"}, status=400)
    bindings, _resolved, target_servers = _binding_context(request.user, data.get("inventory_bindings"))
    try:
        evaluation = evaluate_compatibility_apply(
            source=source,
            adapted_yaml=adapted_yaml,
            snapshot=snapshot,
            bindings=bindings,
            target_servers=target_servers,
            syntax_validator=validate_playbook_syntax,
        )
    except CompatibilityApplyEvaluationError as exc:
        payload = {"success": False, "error": str(exc), "code": exc.code}
        if exc.details:
            payload["details"] = exc.details
        return JsonResponse(payload, status=exc.status)
    try:
        revision, saved_draft = persist_compatibility_apply(
            playbook=playbook,
            actor=request.user,
            draft=draft,
            snapshot=snapshot,
            current_base=current_base,
            data=data,
            bindings=bindings,
            source=source,
            evaluation=evaluation,
        )
    except (DraftConflict, BundleValidationError) as exc:
        if isinstance(exc, BundleValidationError) and exc.code != "playbook_draft_conflict":
            return JsonResponse(
                {"success": False, "error": str(exc), "code": exc.code, "details": exc.details},
                status=exc.status_code,
            )
        _latest, latest_snapshot, latest_base = _editable_draft_base(
            playbook, actor=request.user, path=expectation.path
        )
        del latest_snapshot
        return _stale_response(current=latest_base)
    payload = compatibility_revision_payload(revision)
    if evaluation.status != "validated":
        return JsonResponse(
            {
                "success": False,
                "error": compatibility_failure_message(evaluation.guard, evaluation.report),
                "revision": payload,
            },
            status=400,
        )
    return JsonResponse(
        {
            "success": True,
            "revision": payload,
            "draft": serialize_draft(saved_draft),
            "applied_from": current_base,
        }
    )


@login_required
@require_feature("automation")
@require_http_methods(["GET"])
def playbook_compatibility_revisions(request, playbook_id: int):
    playbook = get_object_or_404(_playbooks_for_user(request.user), id=playbook_id)
    revisions = playbook.compatibility_revisions.filter(user=request.user)[:20]
    return JsonResponse(
        {
            "success": True,
            "revisions": [
                {
                    "id": revision.id,
                    "status": revision.status,
                    "report": revision.report,
                    "semantic_guard": revision.semantic_guard,
                    "change_summary": revision.change_summary,
                    "created_at": revision.created_at.isoformat(),
                    "active": playbook.active_compatibility_revision_id == revision.id,
                }
                for revision in revisions
            ],
        }
    )
