"""Compatibility analysis, guarded AI adaptation, and revision APIs."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_http_methods

from core_ui.ai_model_policy import operational_provider_binding
from core_ui.decorators import require_feature
from servers.models import Playbook, PlaybookCompatibilityRevision
from servers.services.playbook_compatibility_ai import PlaybookAdaptationError, adapt_playbook_with_ai
from servers.services.playbook_compatibility_analysis import analyze_playbook_compatibility, compare_semantics
from servers.services.playbook_compatibility_inventory import normalize_inventory_bindings
from servers.services.playbook_compatibility_validation import validate_playbook_syntax
from servers.services.playbook_runner import resolve_target_servers
from servers.services.playbooks.access import capabilities_for, playbooks_visible_to
from servers.services.playbooks.revisions import (
    create_compatibility_adaptation_revision,
    ensure_playbook_workspace,
)
from servers.services.playbooks.serialization import serialize_revision
from servers.views.server_playbook_serializers import _playbooks_for_user, _serialize_playbook


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


def _compatibility_failure_message(guard: dict[str, Any], report: dict[str, Any]) -> str:
    if not guard.get("passed"):
        violations = [str(item) for item in guard.get("violations") or [] if str(item).strip()]
        detail = "; ".join(violations[:3]) or "protected playbook logic changed"
        return f"AI patch rejected: {detail}"
    blockers = [
        str(item.get("message") or item.get("code") or "Unknown blocker")
        for item in report.get("issues") or []
        if item.get("severity") == "error"
    ]
    if blockers:
        return "Adaptation blocked: " + "; ".join(blockers[:3])
    return "Adaptation failed an unknown compatibility check"


def _source_from_payload(data: dict[str, Any]) -> str:
    return str(data.get("source_yaml") or "").strip()


def _validate_source_payload(source: str) -> JsonResponse | None:
    if not source:
        return JsonResponse({"success": False, "error": "Ansible YAML is required"}, status=400)
    if len(source) > 200_000:
        return JsonResponse({"success": False, "error": "Playbook YAML is too large"}, status=413)
    return None


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
        report["syntax_check"] = validate_playbook_syntax(source, allow_dependency_setup=False)
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
    published_source = (
        playbook.published_revision.source_yaml if playbook.published_revision_id else playbook.source_yaml
    )
    source = str(
        data.get("source_yaml") if capabilities.can_edit and "source_yaml" in data else published_source or ""
    ).strip()
    if not source:
        return JsonResponse({"success": False, "error": "Playbook has no imported Ansible YAML"}, status=400)
    if len(source) > 200_000:
        return JsonResponse({"success": False, "error": "Playbook YAML is too large"}, status=413)
    report = analyze_playbook_compatibility(source, bindings=bindings, target_servers=target_servers)
    if bool(data.get("syntax_check", True)) and not any(
        item.get("severity") == "error" for item in report.get("issues") or []
    ):
        report["syntax_check"] = validate_playbook_syntax(source, allow_dependency_setup=False)
    if playbook.user_id == request.user.id and source == (playbook.source_yaml or "").strip():
        Playbook.objects.filter(pk=playbook.pk).update(compatibility=report)
    return JsonResponse({"success": True, "report": report})


@login_required
@require_feature("automation")
@require_http_methods(["POST"])
def playbook_compatibility_adapt(request, playbook_id: int):
    playbook = get_object_or_404(Playbook, id=playbook_id, user=request.user)
    data = _json_body(request)
    bindings, _resolved, target_servers = _binding_context(request.user, data.get("inventory_bindings"))
    source = (playbook.source_yaml or "").strip()
    if not source:
        return JsonResponse({"success": False, "error": "Playbook has no imported Ansible YAML"}, status=400)
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
def playbook_compatibility_apply(request, playbook_id: int):
    playbook = get_object_or_404(Playbook, id=playbook_id, user=request.user)
    # Establish the legacy source as the published origin before activating a
    # newly accepted compatibility record. Otherwise lazy workspace migration
    # could mistake this new proposal for historical published state.
    ensure_playbook_workspace(playbook, actor=request.user)
    data = _json_body(request)
    source = (playbook.source_yaml or "").strip()
    adapted_yaml = str(data.get("adapted_yaml") or "").strip()
    if not source or not adapted_yaml:
        return JsonResponse({"success": False, "error": "source and adapted YAML are required"}, status=400)
    if len(adapted_yaml) > 200_000:
        return JsonResponse({"success": False, "error": "Adapted YAML is too large"}, status=400)
    bindings, _resolved, target_servers = _binding_context(request.user, data.get("inventory_bindings"))
    guard = compare_semantics(source, adapted_yaml)
    report = analyze_playbook_compatibility(adapted_yaml, bindings=bindings, target_servers=target_servers)
    if guard["passed"] and not any(item.get("severity") == "error" for item in report.get("issues") or []):
        report["syntax_check"] = validate_playbook_syntax(adapted_yaml, allow_dependency_setup=False)
        if report["syntax_check"].get("passed") is False:
            report.setdefault("issues", []).append(
                {
                    "code": "ansible_syntax_check",
                    "severity": "error",
                    "message": report["syntax_check"].get("message") or "Ansible syntax check failed",
                    "path": "playbook",
                }
            )
    has_blocker = any(item.get("severity") == "error" for item in report.get("issues") or [])
    status = (
        PlaybookCompatibilityRevision.STATUS_VALIDATED
        if guard["passed"] and not has_blocker
        else PlaybookCompatibilityRevision.STATUS_REJECTED
    )
    revision = PlaybookCompatibilityRevision.objects.create(
        playbook=playbook,
        user=request.user,
        source_hash=hashlib.sha256(source.encode("utf-8")).hexdigest(),
        adapted_yaml=adapted_yaml,
        inventory_bindings=bindings,
        report=report,
        semantic_guard=guard,
        change_summary=[str(item) for item in data.get("changes") or []][:20],
        status=status,
    )
    result_revision = None
    if status == PlaybookCompatibilityRevision.STATUS_VALIDATED:
        playbook.active_compatibility_revision = revision
        playbook.compatibility = report
        playbook.save(update_fields=["active_compatibility_revision", "compatibility", "updated_at"])
        result_revision = create_compatibility_adaptation_revision(playbook, revision, actor=request.user)
    payload = {
        "id": revision.id,
        "status": revision.status,
        "report": revision.report,
        "semantic_guard": revision.semantic_guard,
        "change_summary": revision.change_summary,
        "created_at": revision.created_at.isoformat(),
    }
    if status != PlaybookCompatibilityRevision.STATUS_VALIDATED:
        return JsonResponse(
            {"success": False, "error": _compatibility_failure_message(guard, report), "revision": payload},
            status=400,
        )
    playbook.refresh_from_db()
    return JsonResponse(
        {
            "success": True,
            "revision": payload,
            "result_revision_id": result_revision.id,
            "content_revision": serialize_revision(result_revision, include_content=True),
            "playbook": _serialize_playbook(playbook, viewer=request.user),
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
