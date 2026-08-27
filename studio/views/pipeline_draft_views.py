"""
Persisted AI draft endpoints for Studio pipeline automation.
"""

from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from core_ui.decorators import require_feature
from studio.model_policy import sanitize_pipeline_graph_selection_for_user, sanitize_pipeline_nodes_for_user
from studio.models import CURRENT_PIPELINE_GRAPH_VERSION, Pipeline, PipelineDraftSession
from studio.pipeline.pipeline_validation import validate_pipeline_definition
from studio.services.pipeline_assistant_interview import (
    build_revision_interview_message,
    merge_revision_goal,
)
from studio.views.common import (
    STUDIO_FEATURE_PIPELINES,
    _err,
    _json_body,
    _ok,
)
from studio.views.pipeline_assistant_views import _build_assistant_response_for_payload
from studio.views.pipeline_draft_helpers import (
    CLOSED_DRAFT_STATUSES,
    draft_queryset_for_user,
    get_draft_for_user,
    latest_revision_graph,
    revision_from_response,
    template_revision_response,
    validate_latest_draft_revision,
)
from studio.views.pipeline_helpers import _pipeline_queryset_for_user


@require_feature(STUDIO_FEATURE_PIPELINES)
def api_pipeline_drafts(request):
    if request.method == "GET":
        drafts = draft_queryset_for_user(request.user)[:25]
        return _ok([draft.to_dict(include_latest=True) for draft in drafts])

    if request.method != "POST":
        return _err("Method not allowed", 405)

    data = _json_body(request)
    response, meta, error = _build_assistant_response_for_payload(request, data)
    if error is not None:
        return error

    source_pipeline = meta["pipeline"]
    snapshot_nodes, snapshot_selected_node = sanitize_pipeline_graph_selection_for_user(
        request.user,
        meta["nodes"],
        meta["selected_node"],
    )
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
            "nodes": snapshot_nodes,
            "edges": meta["edges"],
            "selected_node": snapshot_selected_node,
        },
        selected_node_id=meta["selected_node_id"],
    )
    revision_from_response(
        session=session,
        user_message=meta["user_message"],
        response=response,
        preview_nodes=meta["preview_nodes"],
        preview_edges=meta["preview_edges"],
    )
    return _ok(session.to_dict(include_latest=True), status=201)


@require_feature(STUDIO_FEATURE_PIPELINES)
def api_pipeline_draft_detail(request, draft_id: int):
    draft = get_draft_for_user(request.user, draft_id)
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
    draft = get_draft_for_user(request.user, draft_id)
    if draft is None:
        return _err("Draft not found", 404)
    if draft.status in CLOSED_DRAFT_STATUSES:
        return _err("Draft is already closed")

    data = _json_body(request)
    base_nodes, base_edges = latest_revision_graph(draft)
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
            (
                node
                for node in payload["nodes"]
                if isinstance(node, dict) and str(node.get("id") or "") == draft.selected_node_id
            ),
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
    snapshot_nodes, snapshot_selected_node = sanitize_pipeline_graph_selection_for_user(
        request.user,
        meta["nodes"],
        meta["selected_node"],
    )
    draft.current_graph_snapshot = {
        "pipeline_id": draft.source_pipeline_id,
        "pipeline_name": meta["pipeline_name"],
        "nodes": snapshot_nodes,
        "edges": meta["edges"],
        "selected_node": snapshot_selected_node,
    }
    draft.selected_node_id = meta["selected_node_id"]
    draft.save(
        update_fields=["title", "user_goal", "intent", "current_graph_snapshot", "selected_node_id", "updated_at"]
    )
    revision_from_response(
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
    draft = get_draft_for_user(request.user, draft_id)
    if draft is None:
        return _err("Draft not found", 404)
    if draft.status in CLOSED_DRAFT_STATUSES:
        return _err("Draft is already closed")

    latest = draft.latest_revision()
    if latest is None:
        return _err("Draft has no revisions")

    result = validate_latest_draft_revision(draft, latest)
    return _ok({"draft": draft.to_dict(include_latest=True), **result})


@require_feature(STUDIO_FEATURE_PIPELINES)
@require_http_methods(["POST"])
def api_pipeline_draft_use_template(request, draft_id: int):
    draft = get_draft_for_user(request.user, draft_id)
    if draft is None:
        return _err("Draft not found", 404)
    if draft.status in CLOSED_DRAFT_STATUSES:
        return _err("Draft is already closed")

    data = _json_body(request)
    template_slug = str(data.get("template_slug") or "").strip()
    if not template_slug:
        return _err("template_slug is required")

    response, preview_nodes, preview_edges, error = template_revision_response(
        draft=draft,
        template_slug=template_slug,
    )
    if error is not None:
        return _err(error, 404)

    revision_from_response(
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
    draft = get_draft_for_user(request.user, draft_id)
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
    nodes = sanitize_pipeline_nodes_for_user(request.user, latest.preview_nodes or [])
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
