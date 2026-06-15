"""
Persisted AI draft endpoints for Studio pipeline automation.
"""

from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from core_ui.decorators import require_feature
from studio.models import (
    CURRENT_PIPELINE_GRAPH_VERSION,
    Pipeline,
    PipelineDraftRevision,
    PipelineDraftSession,
)
from studio.pipeline_validation import validate_pipeline_definition
from studio.services import list_owned_server_payloads
from studio.services.pipeline_assistant_interview import (
    build_revision_interview_message,
    merge_revision_goal,
)
from studio.services.pipeline_template_recommendations import (
    build_template_graph_patch,
    build_template_resource_plan,
    get_pilot_pipeline_template,
    recommend_pilot_pipeline_templates,
)
from studio.skill_registry import list_skills
from studio.views.pipeline_assistant_preview import apply_pipeline_assistant_patch, pipeline_assistant_risk
from studio.views.common import (
    STUDIO_FEATURE_MCP,
    STUDIO_FEATURE_PIPELINES,
    STUDIO_FEATURE_SKILLS,
    _err,
    _json_body,
    _ok,
    _user_has_feature,
)
from studio.views.mcp_views import _mcp_read_queryset_for_user
from studio.views.pipeline_assistant_views import _build_assistant_response_for_payload
from studio.views.pipeline_helpers import _pipeline_queryset_for_user
from studio.views.skill_helpers import _can_read_skill, _skill_access_map, _skill_to_summary_dict

CLOSED_DRAFT_STATUSES = {
    PipelineDraftSession.STATUS_APPLIED,
    PipelineDraftSession.STATUS_DISCARDED,
}


def _draft_queryset_for_user(user):
    qs = PipelineDraftSession.objects.select_related("owner", "source_pipeline", "applied_pipeline").prefetch_related("revisions")
    if getattr(user, "is_staff", False):
        return qs.order_by("-updated_at", "-id")
    return qs.filter(owner=user).order_by("-updated_at", "-id")


def _get_draft(request, draft_id: int) -> PipelineDraftSession | None:
    return _draft_queryset_for_user(request.user).filter(pk=draft_id).first()


def _assistant_status(response: dict) -> str:
    if response.get("validation", {}).get("ok") is False:
        return PipelineDraftSession.STATUS_INVALID
    if response.get("risk", {}).get("level") == "dangerous":
        return PipelineDraftSession.STATUS_BLOCKED
    if response.get("questions"):
        return PipelineDraftSession.STATUS_NEEDS_INPUT
    return PipelineDraftSession.STATUS_READY


def _revision_from_response(
    *,
    session: PipelineDraftSession,
    user_message: str,
    response: dict,
    preview_nodes: list[dict],
    preview_edges: list[dict],
) -> PipelineDraftRevision:
    revision = PipelineDraftRevision.objects.create(
        session=session,
        user_message=user_message,
        assistant_reply=str(response.get("reply") or ""),
        target_node_id=str(response.get("target_node_id") or ""),
        node_patch=response.get("node_patch") if isinstance(response.get("node_patch"), dict) else {},
        graph_patch=response.get("graph_patch") if isinstance(response.get("graph_patch"), dict) else {},
        preview_nodes=preview_nodes,
        preview_edges=preview_edges,
        validation=response.get("validation") if isinstance(response.get("validation"), dict) else {},
        risk=response.get("risk") if isinstance(response.get("risk"), dict) else {},
        requirements=response.get("requirements") if isinstance(response.get("requirements"), list) else [],
        assumptions=response.get("assumptions") if isinstance(response.get("assumptions"), list) else [],
        questions=response.get("questions") if isinstance(response.get("questions"), list) else [],
        resource_plan=response.get("resource_plan") if isinstance(response.get("resource_plan"), dict) else {},
        node_explanations=response.get("node_explanations") if isinstance(response.get("node_explanations"), dict) else {},
        warnings=response.get("warnings") if isinstance(response.get("warnings"), list) else [],
        patch_summary=str(response.get("patch_summary") or ""),
        suggested_next_actions=(
            response.get("suggested_next_actions") if isinstance(response.get("suggested_next_actions"), list) else []
        ),
        confidence=response.get("confidence") if isinstance(response.get("confidence"), (int, float)) else None,
        response_payload=response,
    )
    session.status = _assistant_status(response)
    session.save(update_fields=["status", "updated_at"])
    return revision


def _latest_revision_graph(session: PipelineDraftSession) -> tuple[list, list]:
    latest = session.latest_revision()
    if latest:
        return latest.preview_nodes or [], latest.preview_edges or []
    snapshot = session.current_graph_snapshot if isinstance(session.current_graph_snapshot, dict) else {}
    return snapshot.get("nodes") or [], snapshot.get("edges") or []


def _source_snapshot_graph(session: PipelineDraftSession) -> tuple[list, list]:
    snapshot = session.current_graph_snapshot if isinstance(session.current_graph_snapshot, dict) else {}
    return snapshot.get("nodes") or [], snapshot.get("edges") or []


def _draft_validation_owner(draft: PipelineDraftSession):
    if draft.source_pipeline_id and draft.source_pipeline:
        return draft.source_pipeline.owner
    return draft.owner


def _template_binding_context(draft: PipelineDraftSession) -> dict:
    owner = _draft_validation_owner(draft)
    mcps = []
    if _user_has_feature(owner, STUDIO_FEATURE_MCP):
        mcps = [
            {
                "id": mcp.pk,
                "name": mcp.name,
                "description": mcp.description,
                "transport": mcp.transport,
                "last_test_ok": mcp.last_test_ok,
                "owner_id": mcp.owner_id,
            }
            for mcp in _mcp_read_queryset_for_user(owner)
        ]

    available_skills = []
    if _user_has_feature(owner, STUDIO_FEATURE_SKILLS):
        all_skills = list_skills()
        access_map = _skill_access_map([skill.slug for skill in all_skills])
        available_skills = [
            _skill_to_summary_dict(skill, owner, access_map.get(skill.slug.lower()))
            for skill in all_skills
            if _can_read_skill(owner, access_map.get(skill.slug.lower()))
        ]

    return {
        "available_servers": list_owned_server_payloads(owner),
        "available_mcp_servers": mcps,
        "available_skills": available_skills,
        "binding_query": f"{draft.title} {draft.user_goal}".strip(),
        "pipeline_name": draft.title,
        "user_message": draft.user_goal,
        "current_user_id": owner.id,
    }


def _validate_latest_draft_revision(draft: PipelineDraftSession, latest: PipelineDraftRevision) -> dict:
    nodes = latest.preview_nodes or []
    edges = latest.preview_edges or []
    validation_errors = validate_pipeline_definition(
        nodes=nodes,
        edges=edges,
        owner=_draft_validation_owner(draft),
        graph_version=CURRENT_PIPELINE_GRAPH_VERSION,
    )
    validation = {"ok": not validation_errors, "errors": validation_errors, "warnings": []}
    risk = pipeline_assistant_risk(nodes, edges)
    dry_run = {
        "ok": validation["ok"] and risk.get("level") != "dangerous",
        "executed": False,
        "mode": "validate_only",
        "checks": ["graph_contract", "references", "risk_review"],
        "message": (
            "Dry-run validation checked graph structure, references and risk. "
            "It did not execute MCP tools, SSH commands, OPS actions or notifications."
        ),
    }

    response = dict(latest.response_payload or {})
    warnings = list(response.get("warnings") if isinstance(response.get("warnings"), list) else latest.warnings or [])
    dry_run_warning = "Dry-run validation completed without executing runtime actions."
    if dry_run_warning not in warnings:
        warnings.append(dry_run_warning)
    response["validation"] = validation
    response["risk"] = risk
    response["dry_run"] = dry_run
    response["warnings"] = warnings

    latest.validation = validation
    latest.risk = risk
    latest.warnings = warnings
    latest.response_payload = response
    latest.save(update_fields=["validation", "risk", "warnings", "response_payload"])

    draft.status = _assistant_status(response)
    draft.save(update_fields=["status", "updated_at"])
    return {"validation": validation, "risk": risk, "dry_run": dry_run}


def _template_revision_response(
    *,
    draft: PipelineDraftSession,
    template_slug: str,
) -> tuple[dict | None, list[dict], list[dict], str | None]:
    template = get_pilot_pipeline_template(template_slug)
    if template is None:
        return None, [], [], "Unknown pilot template"

    base_nodes, base_edges = _source_snapshot_graph(draft)
    recommendations = recommend_pilot_pipeline_templates(
        user_message=draft.user_goal,
        pipeline_name=draft.title,
        limit=5,
    )
    if not any(item.get("slug") == template_slug for item in recommendations):
        manual_template = {
            "slug": template.get("slug"),
            "name": template.get("name"),
            "description": template.get("description"),
            "category": template.get("category"),
            "tags": template.get("tags") or [],
            "match_score": 0,
            "matched_terms": [],
            "node_types": list(
                dict.fromkeys(
                    str(node.get("type") or "")
                    for node in (template.get("nodes") or [])
                    if isinstance(node, dict) and str(node.get("type") or "")
                )
            ),
        }
        recommendations = [manual_template, *recommendations]

    binding_context = _template_binding_context(draft)
    graph_patch = build_template_graph_patch(template, assistant_context=binding_context)
    preview_nodes, preview_edges = apply_pipeline_assistant_patch(base_nodes, base_edges, {"graph_patch": graph_patch})
    owner = _draft_validation_owner(draft)
    validation_errors = validate_pipeline_definition(
        nodes=preview_nodes,
        edges=preview_edges,
        owner=owner,
        graph_version=CURRENT_PIPELINE_GRAPH_VERSION,
    )
    validation = {"ok": not validation_errors, "errors": validation_errors, "warnings": []}
    risk = pipeline_assistant_risk(preview_nodes, preview_edges)
    template_name = str(template.get("name") or template.get("slug") or "Pilot template")
    response = {
        "reply": f"Selected `{template_name}` as the draft skeleton. Review resources and arguments before applying.",
        "selected_template": {
            "slug": template.get("slug"),
            "name": template_name,
            "source": "manual_template_switch",
        },
        "template_recommendations": recommendations,
        "requirements": [draft.user_goal] if draft.user_goal else [],
        "assumptions": [
            f"Pilot template selected manually: {template.get('slug')}.",
            "Approval, verification and report branches were preserved from the template.",
        ],
        "questions": [],
        "resource_plan": build_template_resource_plan(template, assistant_context=binding_context),
        "target_node_id": None,
        "node_patch": {},
        "graph_patch": graph_patch,
        "node_explanations": {
            str(node.get("ref")): "Step copied from the selected pilot template skeleton."
            for node in graph_patch.get("nodes", [])
            if isinstance(node, dict) and str(node.get("ref") or "")
        },
        "confidence": 0.68,
        "warnings": [],
        "patch_summary": f"Pilot template skeleton: {template_name}",
        "suggested_next_actions": ["Review resources", "Validate / dry-run", "Apply the draft"],
        "validation": validation,
        "risk": risk,
    }
    return response, preview_nodes, preview_edges, None


@require_feature(STUDIO_FEATURE_PIPELINES)
def api_pipeline_drafts(request):
    if request.method == "GET":
        drafts = _draft_queryset_for_user(request.user)[:25]
        return _ok([draft.to_dict(include_latest=True) for draft in drafts])

    if request.method != "POST":
        return _err("Method not allowed", 405)

    data = _json_body(request)
    response, meta, error = _build_assistant_response_for_payload(request, data)
    if error is not None:
        return error

    source_pipeline = meta["pipeline"]
    session = PipelineDraftSession.objects.create(
        owner=request.user,
        source_pipeline=source_pipeline,
        status=PipelineDraftSession.STATUS_DRAFTING,
        intent=meta["intent"],
        title=meta["pipeline_name"],
        user_goal=meta["user_message"],
        current_graph_snapshot={
            "pipeline_id": source_pipeline.id if source_pipeline else None,
            "pipeline_name": meta["pipeline_name"],
            "nodes": meta["nodes"],
            "edges": meta["edges"],
            "selected_node": meta["selected_node"],
        },
        selected_node_id=meta["selected_node_id"],
    )
    _revision_from_response(
        session=session,
        user_message=meta["user_message"],
        response=response,
        preview_nodes=meta["preview_nodes"],
        preview_edges=meta["preview_edges"],
    )
    return _ok(session.to_dict(include_latest=True), status=201)


@require_feature(STUDIO_FEATURE_PIPELINES)
def api_pipeline_draft_detail(request, draft_id: int):
    draft = _get_draft(request, draft_id)
    if draft is None:
        return _err("Draft not found", 404)

    if request.method == "GET":
        return _ok(draft.to_dict(include_latest=True))

    if request.method == "DELETE":
        if draft.status == PipelineDraftSession.STATUS_APPLIED:
            return _err("Applied drafts cannot be discarded")
        draft.status = PipelineDraftSession.STATUS_DISCARDED
        draft.save(update_fields=["status", "updated_at"])
        return _ok(draft.to_dict(include_latest=True))

    return _err("Method not allowed", 405)


@require_feature(STUDIO_FEATURE_PIPELINES)
@require_http_methods(["POST"])
def api_pipeline_draft_revise(request, draft_id: int):
    draft = _get_draft(request, draft_id)
    if draft is None:
        return _err("Draft not found", 404)
    if draft.status in CLOSED_DRAFT_STATUSES:
        return _err("Draft is already closed")

    data = _json_body(request)
    base_nodes, base_edges = _latest_revision_graph(draft)
    latest = draft.latest_revision()
    raw_user_message = str(data.get("user_message") or "").strip()
    previous_questions = latest.questions if latest and isinstance(latest.questions, list) else []
    assistant_user_message = build_revision_interview_message(
        original_goal=draft.user_goal,
        user_message=raw_user_message,
        previous_questions=previous_questions,
    )
    payload = {
        "pipeline_id": draft.source_pipeline_id,
        "pipeline_name": data.get("pipeline_name") or draft.title or "Untitled pipeline",
        "nodes": data.get("nodes") if isinstance(data.get("nodes"), list) else base_nodes,
        "edges": data.get("edges") if isinstance(data.get("edges"), list) else base_edges,
        "selected_node": data.get("selected_node"),
        "user_message": assistant_user_message,
        "intent": data.get("intent") or draft.intent,
        "draft_mode": True,
        "history": data.get("history") or [],
        "last_validation_errors": data.get("last_validation_errors") or [],
        "last_run_summary": data.get("last_run_summary") or {},
    }
    if not payload["selected_node"] and draft.selected_node_id:
        payload["selected_node"] = next(
            (node for node in payload["nodes"] if isinstance(node, dict) and str(node.get("id") or "") == draft.selected_node_id),
            None,
        )

    response, meta, error = _build_assistant_response_for_payload(request, payload)
    if error is not None:
        return error

    draft.title = meta["pipeline_name"]
    draft.user_goal = merge_revision_goal(
        original_goal=draft.user_goal,
        user_message=raw_user_message or meta["user_message"],
        previous_questions=previous_questions,
    )
    draft.intent = meta["intent"]
    draft.current_graph_snapshot = {
        "pipeline_id": draft.source_pipeline_id,
        "pipeline_name": meta["pipeline_name"],
        "nodes": meta["nodes"],
        "edges": meta["edges"],
        "selected_node": meta["selected_node"],
    }
    draft.selected_node_id = meta["selected_node_id"]
    draft.save(update_fields=["title", "user_goal", "intent", "current_graph_snapshot", "selected_node_id", "updated_at"])
    _revision_from_response(
        session=draft,
        user_message=raw_user_message or meta["user_message"],
        response=response,
        preview_nodes=meta["preview_nodes"],
        preview_edges=meta["preview_edges"],
    )
    return _ok(draft.to_dict(include_latest=True))


@require_feature(STUDIO_FEATURE_PIPELINES)
@require_http_methods(["POST"])
def api_pipeline_draft_validate(request, draft_id: int):
    draft = _get_draft(request, draft_id)
    if draft is None:
        return _err("Draft not found", 404)
    if draft.status in CLOSED_DRAFT_STATUSES:
        return _err("Draft is already closed")

    latest = draft.latest_revision()
    if latest is None:
        return _err("Draft has no revisions")

    result = _validate_latest_draft_revision(draft, latest)
    return _ok({"draft": draft.to_dict(include_latest=True), **result})


@require_feature(STUDIO_FEATURE_PIPELINES)
@require_http_methods(["POST"])
def api_pipeline_draft_use_template(request, draft_id: int):
    draft = _get_draft(request, draft_id)
    if draft is None:
        return _err("Draft not found", 404)
    if draft.status in CLOSED_DRAFT_STATUSES:
        return _err("Draft is already closed")

    data = _json_body(request)
    template_slug = str(data.get("template_slug") or "").strip()
    if not template_slug:
        return _err("template_slug is required")

    response, preview_nodes, preview_edges, error = _template_revision_response(
        draft=draft,
        template_slug=template_slug,
    )
    if error is not None:
        return _err(error, 404)

    _revision_from_response(
        session=draft,
        user_message=f"Use pilot template: {template_slug}",
        response=response,
        preview_nodes=preview_nodes,
        preview_edges=preview_edges,
    )
    return _ok(draft.to_dict(include_latest=True))


@require_feature(STUDIO_FEATURE_PIPELINES)
@require_http_methods(["POST"])
def api_pipeline_draft_apply(request, draft_id: int):
    draft = _get_draft(request, draft_id)
    if draft is None:
        return _err("Draft not found", 404)
    if draft.status == PipelineDraftSession.STATUS_DISCARDED:
        return _err("Draft is discarded")
    if draft.status == PipelineDraftSession.STATUS_APPLIED:
        return _err("Draft is already applied")

    latest = draft.latest_revision()
    if latest is None:
        return _err("Draft has no revisions")
    if latest.validation.get("ok") is False:
        return _err("Draft validation must pass before apply")
    if latest.risk.get("level") == "dangerous":
        return _err("Draft contains dangerous actions. Revise it with approval or safer commands before apply.")

    data = _json_body(request)
    create_new = data.get("create_new") is True or draft.source_pipeline_id is None
    title = str(data.get("name") or draft.title or "AI Draft Pipeline").strip()
    description = str(data.get("description") or draft.user_goal or latest.assistant_reply or "").strip()
    icon = str(data.get("icon") or "W").strip() or "W"
    tags = data.get("tags") if isinstance(data.get("tags"), list) else ["ai-draft"]
    nodes = latest.preview_nodes or []
    edges = latest.preview_edges or []

    owner = draft.source_pipeline.owner if draft.source_pipeline_id and draft.source_pipeline else draft.owner
    validation_errors = validate_pipeline_definition(
        nodes=nodes,
        edges=edges,
        owner=owner,
        graph_version=CURRENT_PIPELINE_GRAPH_VERSION,
    )
    if validation_errors:
        return JsonResponse(
            {"error": "Pipeline validation failed: " + "; ".join(validation_errors), "details": validation_errors},
            status=400,
        )

    if create_new:
        pipeline = Pipeline.objects.create(
            name=title,
            description=description,
            icon=icon,
            tags=tags,
            nodes=nodes,
            edges=edges,
            graph_version=CURRENT_PIPELINE_GRAPH_VERSION,
            owner=draft.owner,
        )
    else:
        pipeline = _pipeline_queryset_for_user(request.user).filter(pk=draft.source_pipeline_id).first()
        if pipeline is None:
            return _err("Source pipeline not found", 404)
        pipeline.name = title or pipeline.name
        pipeline.description = description
        pipeline.nodes = nodes
        pipeline.edges = edges
        pipeline.graph_version = CURRENT_PIPELINE_GRAPH_VERSION
        pipeline.save()

    pipeline.sync_triggers_from_nodes()
    draft.status = PipelineDraftSession.STATUS_APPLIED
    draft.applied_pipeline = pipeline
    draft.applied_at = timezone.now()
    draft.save(update_fields=["status", "applied_pipeline", "applied_at", "updated_at"])
    return _ok({"draft": draft.to_dict(include_latest=True), "pipeline": pipeline.to_detail_dict()})
