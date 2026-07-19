from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from django.utils import timezone

from app.assistant_actions import (
    AssistantActionContext,
    AssistantActionError,
)
from core_ui.access import feature_allowed_for_user
from studio.capability_registry import build_studio_capability_registry
from studio.models import CURRENT_PIPELINE_GRAPH_VERSION, Pipeline, PipelineDraftSession, PipelineRun, PipelineTrigger
from studio.pipeline_preflight import pipeline_integration_diagnostics
from studio.pipeline_runtime import get_executor_for_run, update_runtime_control
from studio.pipeline_runtime_context import validate_pipeline_entry_branch, validate_pipeline_runtime_context
from studio.pipeline_validation import ensure_json_object, validate_pipeline_definition
from studio.readiness_issues import runtime_limit_issue, validation_issues
from studio.skill_authoring import validate_skills
from studio.skill_registry import list_skills, normalise_skill_slugs
from studio.trigger_dispatch import get_pipeline_run_limit_error, pipeline_run_creation_error_details
from studio.views.mcp_views import _mcp_read_queryset_for_user, _mcp_to_dict
from studio.views.pipeline_assistant_preview import pipeline_assistant_risk
from studio.views.pipeline_assistant_views import _build_assistant_response_for_payload
from studio.views.pipeline_draft_helpers import (
    CLOSED_DRAFT_STATUSES,
    draft_queryset_for_user,
    get_draft_for_user,
    latest_revision_graph,
    revision_from_response,
    validate_latest_draft_revision,
)
from studio.views.pipeline_helpers import (
    _create_pipeline_run,
    _launch_pipeline_run,
    _pipeline_queryset_for_user,
    _resolve_manual_entry_trigger,
)
from studio.views.run_views import _run_queryset_for_user
from studio.views.skill_helpers import (
    _can_edit_skill,
    _can_read_skill,
    _ensure_skill_access,
    _get_skill_access,
    _skill_access_map,
    _skill_dir_from_slug,
    _skill_to_detail_dict,
    _skill_to_summary_dict,
)
from studio.skill_authoring import scaffold_skill, validate_skill_dir
from studio.skill_registry import SkillNotFoundError, get_skill
from studio.services.pipeline_assistant_interview import (
    build_revision_interview_message,
    merge_revision_goal,
)
from studio.views.skill_views import (
    _has_skill_metadata_update,
    _render_skill_metadata,
    _update_skill_metadata_file,
)


def _request_like(user):
    return SimpleNamespace(user=user)


def _int_payload(ctx: AssistantActionContext, key: str) -> int:
    value = ctx.input_payload.get(key)
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise AssistantActionError(f"{key} must be an integer") from exc
    if parsed <= 0:
        raise AssistantActionError(f"{key} must be positive")
    return parsed


def _pipeline_for_user(user, pipeline_id: int) -> Pipeline:
    pipeline = _pipeline_queryset_for_user(user).filter(pk=pipeline_id).first()
    if pipeline is None:
        raise AssistantActionError("Pipeline not found", status=404)
    return pipeline


def _draft_for_user(user, draft_id: int) -> PipelineDraftSession:
    draft = get_draft_for_user(user, draft_id)
    if draft is None:
        raise AssistantActionError("Draft not found", status=404)
    return draft


def _run_for_user(user, run_id: int) -> PipelineRun:
    run = _run_queryset_for_user(user).filter(pk=run_id).first()
    if run is None:
        raise AssistantActionError("Run not found", status=404)
    return run


def _target_url(path: str) -> str:
    return {"target_url": path}


def list_pipelines(ctx: AssistantActionContext) -> dict[str, Any]:
    query = str(ctx.input_payload.get("q") or "").strip()
    qs = _pipeline_queryset_for_user(ctx.user)
    if query:
        qs = qs.filter(name__icontains=query)
    items = [pipeline.to_list_dict() for pipeline in qs[:25]]
    return {"pipelines": items, "count": len(items), "target_url": "/studio"}


def list_runs(ctx: AssistantActionContext) -> dict[str, Any]:
    runs = [_run.to_dict() for _run in _run_queryset_for_user(ctx.user)[:25]]
    return {"runs": runs, "count": len(runs), "target_url": "/studio/runs"}


def capability_registry(ctx: AssistantActionContext) -> dict[str, Any]:
    server_count = ctx.input_payload.get("server_count")
    try:
        parsed_server_count = int(server_count) if server_count not in (None, "") else None
    except (TypeError, ValueError) as exc:
        raise AssistantActionError("server_count must be an integer") from exc
    return {
        "capability_registry": build_studio_capability_registry(ctx.user, server_count=parsed_server_count),
        "target_url": "/studio",
    }


def list_mcp_servers(ctx: AssistantActionContext) -> dict[str, Any]:
    query = str(ctx.input_payload.get("q") or "").strip().lower()
    items = []
    for mcp in _mcp_read_queryset_for_user(ctx.user)[:50]:
        payload = _mcp_to_dict(mcp, ctx.user)
        blob = " ".join(str(payload.get(key) or "") for key in ("name", "description", "transport", "url", "command")).lower()
        if query and query not in blob:
            continue
        items.append(payload)
    return {"mcp_servers": items[:25], "count": len(items), "target_url": "/studio/mcp"}


def list_studio_skills(ctx: AssistantActionContext) -> dict[str, Any]:
    query = str(ctx.input_payload.get("q") or "").strip().lower()
    skills = list_skills()
    access_map = _skill_access_map([skill.slug for skill in skills])
    items = []
    for skill in skills:
        access = access_map.get(skill.slug.lower())
        if not _can_read_skill(ctx.user, access):
            continue
        payload = _skill_to_summary_dict(skill, ctx.user, access)
        blob = " ".join(
            str(payload.get(key) or "")
            for key in ("slug", "name", "description", "service", "category", "safety_level")
        ).lower()
        if query and query not in blob:
            continue
        items.append(payload)
    return {"skills": items[:50], "count": len(items), "target_url": "/studio/skills"}


def validate_studio_skills(ctx: AssistantActionContext) -> dict[str, Any]:
    raw_slugs = ctx.input_payload.get("slugs")
    if isinstance(raw_slugs, str):
        raw_slugs = [raw_slugs]
    slugs = normalise_skill_slugs(raw_slugs if isinstance(raw_slugs, list) else [])
    strict = bool(ctx.input_payload.get("strict"))
    if slugs:
        access_map = _skill_access_map(slugs)
        denied = [
            slug
            for slug in slugs
            if not _can_read_skill(ctx.user, access_map.get(slug.lower()))
        ]
        if denied:
            raise AssistantActionError(f"Skills not accessible: {', '.join(denied)}", status=403)
        results = validate_skills(slugs)
    else:
        skills = list_skills()
        access_map = _skill_access_map([skill.slug for skill in skills])
        visible_slugs = [
            skill.slug
            for skill in skills
            if _can_read_skill(ctx.user, access_map.get(skill.slug.lower()))
        ]
        results = validate_skills(visible_slugs) if visible_slugs else []
    error_count = sum(len(item.errors) for item in results)
    warning_count = sum(len(item.warnings) for item in results)
    return {
        "results": [item.to_dict() for item in results],
        "summary": {
            "skills": len(results),
            "errors": error_count,
            "warnings": warning_count,
            "is_valid": error_count == 0 and (warning_count == 0 if strict else True),
            "strict": strict,
        },
        "target_url": "/studio/skills",
    }


def create_pipeline_draft(ctx: AssistantActionContext) -> dict[str, Any]:
    title = str(ctx.input_payload.get("pipeline_name") or "").strip() or "AI Chat Pipeline"
    user_message = str(ctx.input_payload.get("user_message") or "").strip()
    if not user_message:
        raise AssistantActionError("user_message is required")

    data = {
        "pipeline_name": title,
        "nodes": ctx.input_payload.get("nodes") if isinstance(ctx.input_payload.get("nodes"), list) else [],
        "edges": ctx.input_payload.get("edges") if isinstance(ctx.input_payload.get("edges"), list) else [],
        "user_message": user_message,
        "intent": str(ctx.input_payload.get("intent") or "create"),
        "draft_mode": True,
    }
    compiler_mode = str(ctx.input_payload.get("compiler_mode") or "").strip()
    if compiler_mode:
        data["compiler_mode"] = compiler_mode

    response, meta, error = _build_assistant_response_for_payload(_request_like(ctx.user), data)
    if error is not None:
        try:
            message = error.content.decode("utf-8")
        except Exception:
            message = "Pipeline assistant failed"
        raise AssistantActionError(message, status=getattr(error, "status_code", 400))

    source_pipeline = meta["pipeline"]
    session = PipelineDraftSession.objects.create(
        owner=ctx.user,
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
    revision_from_response(
        session=session,
        user_message=meta["user_message"],
        response=response,
        preview_nodes=meta["preview_nodes"],
        preview_edges=meta["preview_edges"],
    )
    return {"draft": session.to_dict(include_latest=True), "target_url": f"/studio/drafts?draft={session.pk}"}


def validate_pipeline_draft(ctx: AssistantActionContext) -> dict[str, Any]:
    draft = _draft_for_user(ctx.user, _int_payload(ctx, "draft_id"))
    latest = draft.latest_revision()
    if latest is None:
        raise AssistantActionError("Draft has no revisions")
    result = validate_latest_draft_revision(draft, latest)
    return {"draft": draft.to_dict(include_latest=True), **result, "target_url": f"/studio/drafts?draft={draft.pk}"}


def apply_pipeline_draft(ctx: AssistantActionContext) -> dict[str, Any]:
    draft = _draft_for_user(ctx.user, _int_payload(ctx, "draft_id"))
    if draft.status == PipelineDraftSession.STATUS_DISCARDED:
        raise AssistantActionError("Draft is discarded")
    if draft.status == PipelineDraftSession.STATUS_APPLIED:
        raise AssistantActionError("Draft is already applied")
    latest = draft.latest_revision()
    if latest is None:
        raise AssistantActionError("Draft has no revisions")
    if latest.validation.get("ok") is False:
        raise AssistantActionError("Draft validation must pass before apply")
    if latest.risk.get("level") == "dangerous":
        raise AssistantActionError("Draft contains dangerous actions. Revise it with approval or safer commands before apply.")

    create_new = ctx.input_payload.get("create_new") is not False or draft.source_pipeline_id is None
    title = str(ctx.input_payload.get("name") or draft.title or "AI Chat Pipeline").strip()
    description = str(ctx.input_payload.get("description") or draft.user_goal or latest.assistant_reply or "").strip()
    tags = ctx.input_payload.get("tags") if isinstance(ctx.input_payload.get("tags"), list) else ["ai-chat"]
    nodes = latest.preview_nodes or []
    edges = latest.preview_edges or []
    owner = draft.source_pipeline.owner if draft.source_pipeline_id and draft.source_pipeline else draft.owner
    errors = validate_pipeline_definition(
        nodes=nodes,
        edges=edges,
        owner=owner,
        graph_version=CURRENT_PIPELINE_GRAPH_VERSION,
    )
    if errors:
        raise AssistantActionError("Pipeline validation failed: " + "; ".join(errors), details={"errors": errors})

    if create_new:
        pipeline = Pipeline.objects.create(
            name=title,
            description=description,
            icon=str(ctx.input_payload.get("icon") or "W")[:8] or "W",
            tags=tags,
            nodes=nodes,
            edges=edges,
            graph_version=CURRENT_PIPELINE_GRAPH_VERSION,
            owner=draft.owner,
        )
    else:
        pipeline = _pipeline_queryset_for_user(ctx.user).filter(pk=draft.source_pipeline_id).first()
        if pipeline is None:
            raise AssistantActionError("Source pipeline not found", status=404)
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
    return {"draft": draft.to_dict(include_latest=True), "pipeline": pipeline.to_detail_dict(), "target_url": f"/studio/pipeline/{pipeline.pk}"}


def _pipeline_run_check(pipeline: Pipeline, *, context: dict[str, Any], entry_node_id: str, validate_only: bool) -> dict[str, Any]:
    validation_errors = validate_pipeline_definition(
        nodes=pipeline.nodes,
        edges=pipeline.edges,
        owner=pipeline.owner,
        graph_version=pipeline.graph_version,
        require_manual_trigger=True,
    )
    selected_trigger = None
    trigger_errors: list[str] = []
    if not validation_errors:
        selected_trigger, trigger_errors = _resolve_manual_entry_trigger(pipeline, entry_node_id)
    branch_errors = (
        validate_pipeline_entry_branch(pipeline.nodes, pipeline.edges, selected_trigger.node_id)
        if selected_trigger is not None
        else []
    )
    context_errors = (
        validate_pipeline_runtime_context(
            pipeline.nodes,
            context,
            edges=pipeline.edges,
            entry_node_id=selected_trigger.node_id,
        )
        if selected_trigger is not None and not branch_errors
        else []
    )
    integration = (
        pipeline_integration_diagnostics(pipeline, entry_node_id=selected_trigger.node_id)
        if selected_trigger is not None and not validation_errors
        else {"requirements": [], "issues": [], "errors": [], "warnings": []}
    )
    limit_error = get_pipeline_run_limit_error(pipeline.owner, cleanup_stale=not validate_only)
    limit_errors = [str(limit_error.get("error") or "Runtime limit reached.")] if limit_error else []
    limit_issues = [runtime_limit_issue(limit_error)] if limit_error else []
    all_errors = [*validation_errors, *trigger_errors, *branch_errors, *context_errors, *integration["errors"], *limit_errors]
    risk = pipeline_assistant_risk(pipeline.nodes, pipeline.edges)
    issues = [*validation_issues([*validation_errors, *trigger_errors, *branch_errors, *context_errors]), *integration["issues"], *limit_issues]
    validation = {"ok": not all_errors, "errors": all_errors, "issues": issues}
    return {
        "selected_trigger": selected_trigger,
        "validation": validation,
        "integration": integration,
        "risk": risk,
        "all_errors": all_errors,
    }


def validate_pipeline_run(ctx: AssistantActionContext) -> dict[str, Any]:
    pipeline = _pipeline_for_user(ctx.user, _int_payload(ctx, "pipeline_id"))
    raw_context, error = ensure_json_object(ctx.input_payload.get("context", {}), label="context")
    if error:
        raise AssistantActionError(error)
    entry_node_id = str(ctx.input_payload.get("entry_node_id") or "").strip()
    check = _pipeline_run_check(pipeline, context=raw_context, entry_node_id=entry_node_id, validate_only=True)
    dry_run = {
        "ok": check["validation"]["ok"] and check["risk"].get("level") != "dangerous",
        "executed": False,
        "mode": "validate_only",
        "checks": ["graph_contract", "manual_trigger", "references", "risk_review", "runtime_context", "integrations", "runtime_limits"],
        "message": "Dry-run validation completed without creating a pipeline run.",
    }
    selected_trigger = check["selected_trigger"]
    return {
        "ok": check["validation"]["ok"],
        "validation": check["validation"],
        "integration_requirements": check["integration"]["requirements"],
        "risk": check["risk"],
        "dry_run": dry_run,
        "entry_node_id": selected_trigger.node_id if selected_trigger else entry_node_id,
        "would_create_run": False,
        "target_url": f"/studio/pipeline/{pipeline.pk}",
    }


def run_pipeline(ctx: AssistantActionContext) -> dict[str, Any]:
    pipeline = _pipeline_for_user(ctx.user, _int_payload(ctx, "pipeline_id"))
    raw_context, error = ensure_json_object(ctx.input_payload.get("context", {}), label="context")
    if error:
        raise AssistantActionError(error)
    entry_node_id = str(ctx.input_payload.get("entry_node_id") or "").strip()
    check = _pipeline_run_check(pipeline, context=raw_context, entry_node_id=entry_node_id, validate_only=False)
    if check["all_errors"]:
        raise AssistantActionError("Pipeline is not runnable: " + "; ".join(check["all_errors"]), details={"validation": check["validation"]})
    selected_trigger = check["selected_trigger"]
    if selected_trigger is None:
        raise AssistantActionError("Pipeline has no runnable manual trigger")
    try:
        run = _create_pipeline_run(
            pipeline=pipeline,
            triggered_by=ctx.user,
            trigger=selected_trigger,
            context=raw_context,
            trigger_data={
                "source": "assistant_chat",
                "trigger_type": PipelineTrigger.TYPE_MANUAL,
                "entry_node_id": selected_trigger.node_id,
            },
            entry_node_id=selected_trigger.node_id,
        )
    except ValueError as exc:
        raise AssistantActionError(
            "Pipeline is not runnable: " + "; ".join(pipeline_run_creation_error_details(exc))
        ) from exc
    _launch_pipeline_run(run)
    return {"run": run.to_dict(), "target_url": f"/studio/runs?run={run.pk}"}


def stop_pipeline_run(ctx: AssistantActionContext) -> dict[str, Any]:
    run = _run_for_user(ctx.user, _int_payload(ctx, "run_id"))
    executor = get_executor_for_run(run.id)
    control, stop_delivered = update_runtime_control(run, live_executor=executor, stop_requested=True)
    if run.status in {PipelineRun.STATUS_PENDING, PipelineRun.STATUS_RUNNING}:
        run.status = PipelineRun.STATUS_STOPPED
        run.finished_at = timezone.now()
        run.save(update_fields=["status", "finished_at"])
    return {"ok": True, "live_executor": stop_delivered, "runtime_control": control, "target_url": f"/studio/runs?run={run.pk}"}


def approve_pipeline_node(ctx: AssistantActionContext) -> dict[str, Any]:
    run = _run_for_user(ctx.user, _int_payload(ctx, "run_id"))
    node_id = str(ctx.input_payload.get("node_id") or "").strip()
    decision = str(ctx.input_payload.get("decision") or "approved").strip().lower()
    response_text = str(ctx.input_payload.get("response_text") or "").strip()
    if not node_id:
        raise AssistantActionError("node_id is required")
    if decision not in {"approved", "rejected"}:
        raise AssistantActionError("decision must be approved or rejected")
    state = dict((run.node_states or {}).get(node_id) or {})
    if not state:
        raise AssistantActionError(f"Node '{node_id}' not found in run #{run.pk}", status=404)
    if state.get("approval_decision"):
        return {"ok": True, "message": f"Already decided: {state['approval_decision']}", "target_url": f"/studio/runs?run={run.pk}"}
    run.node_states[node_id] = {
        **state,
        "approval_decision": decision,
        "approval_response": response_text,
        "decided_at": timezone.now().isoformat(),
    }
    PipelineRun.objects.filter(pk=run.pk).update(node_states=run.node_states)
    return {"ok": True, "decision": decision, "node_id": node_id, "target_url": f"/studio/runs?run={run.pk}"}


def get_pipeline(ctx: AssistantActionContext) -> dict[str, Any]:
    pipeline = _pipeline_for_user(ctx.user, _int_payload(ctx, "pipeline_id"))
    detail = pipeline.to_detail_dict() if hasattr(pipeline, "to_detail_dict") else pipeline.to_list_dict()
    # Keep graph readable for the model without flooding context
    nodes = list(pipeline.nodes or [])
    edges = list(pipeline.edges or [])
    return {
        "pipeline": detail,
        "graph_summary": {
            "node_count": len(nodes),
            "edge_count": len(edges),
            "node_types": sorted(
                {
                    str((n or {}).get("type") or (n or {}).get("data", {}).get("type") or "unknown")
                    for n in nodes
                    if isinstance(n, dict)
                }
            )[:30],
            "node_ids": [str((n or {}).get("id") or "") for n in nodes if isinstance(n, dict)][:40],
        },
        "target_url": f"/studio/pipeline/{pipeline.pk}",
    }


def list_pipeline_drafts(ctx: AssistantActionContext) -> dict[str, Any]:
    drafts = list(draft_queryset_for_user(ctx.user)[:25])
    items = [d.to_dict(include_latest=True) for d in drafts]
    return {"drafts": items, "count": len(items), "target_url": "/studio/drafts"}


def revise_pipeline_draft(ctx: AssistantActionContext) -> dict[str, Any]:
    """Continue configuring a draft with a natural-language instruction.

    Self-bootstrapping: when no draft_id is supplied the first revise call creates
    the draft from the instruction, so the model can start the pipeline flow with a
    single tool even if it skipped pipeline_draft.create.
    """
    raw_draft_id = ctx.input_payload.get("draft_id")
    if raw_draft_id in (None, "", 0, "0"):
        user_message = str(ctx.input_payload.get("user_message") or "").strip()
        if not user_message:
            raise AssistantActionError("user_message is required")
        return create_pipeline_draft(
            AssistantActionContext(
                user=ctx.user,
                input_payload={
                    "user_message": user_message,
                    "pipeline_name": ctx.input_payload.get("pipeline_name"),
                    "intent": "create",
                },
                request=ctx.request,
            )
        )
    draft = _draft_for_user(ctx.user, _int_payload(ctx, "draft_id"))
    if draft.status in CLOSED_DRAFT_STATUSES:
        raise AssistantActionError("Draft is already closed")
    raw_user_message = str(ctx.input_payload.get("user_message") or "").strip()
    if not raw_user_message:
        raise AssistantActionError("user_message is required")

    base_nodes, base_edges = latest_revision_graph(draft)
    latest = draft.latest_revision()
    previous_questions = latest.questions if latest and isinstance(latest.questions, list) else []
    assistant_user_message = build_revision_interview_message(
        original_goal=draft.user_goal,
        user_message=raw_user_message,
        previous_questions=previous_questions,
    )
    payload = {
        "pipeline_id": draft.source_pipeline_id,
        "pipeline_name": str(ctx.input_payload.get("pipeline_name") or draft.title or "Untitled pipeline"),
        "nodes": base_nodes,
        "edges": base_edges,
        "user_message": assistant_user_message,
        "intent": str(ctx.input_payload.get("intent") or draft.intent or "update"),
        "draft_mode": True,
        "history": [],
        "last_validation_errors": [],
        "last_run_summary": {},
    }
    if draft.selected_node_id:
        payload["selected_node"] = next(
            (
                node
                for node in payload["nodes"]
                if isinstance(node, dict) and str(node.get("id") or "") == draft.selected_node_id
            ),
            None,
        )

    response, meta, error = _build_assistant_response_for_payload(_request_like(ctx.user), payload)
    if error is not None:
        try:
            message = error.content.decode("utf-8")
        except Exception:
            message = "Pipeline draft revise failed"
        raise AssistantActionError(message, status=getattr(error, "status_code", 400))

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
    return {
        "draft": draft.to_dict(include_latest=True),
        "assistant_reply": str(response.get("reply") or "")[:2000],
        "patch_summary": str(response.get("patch_summary") or "")[:1000],
        "target_url": f"/studio/drafts?draft={draft.pk}",
    }


def get_studio_skill(ctx: AssistantActionContext) -> dict[str, Any]:
    slug = str(ctx.input_payload.get("slug") or "").strip()
    if not slug:
        raise AssistantActionError("slug is required")
    try:
        skill = get_skill(slug)
    except SkillNotFoundError as exc:
        raise AssistantActionError("Skill not found", status=404) from exc
    access = _get_skill_access(skill.slug)
    if not _can_read_skill(ctx.user, access):
        raise AssistantActionError("Skill not found", status=404)
    detail = _skill_to_detail_dict(skill, ctx.user, access)
    # Truncate body for tool context
    content = str(detail.get("content") or skill.content or "")
    if len(content) > 6000:
        detail["content"] = content[:6000] + "\n…[truncated]"
    return {"skill": detail, "target_url": f"/studio/skills/{skill.slug}"}


def create_studio_skill(ctx: AssistantActionContext) -> dict[str, Any]:
    name = str(ctx.input_payload.get("name") or "").strip()
    description = str(ctx.input_payload.get("description") or "").strip()
    if not name:
        raise AssistantActionError("name is required")
    if not description:
        raise AssistantActionError("description is required")
    if len(description) < 20:
        raise AssistantActionError("description must be at least 20 characters (when to use / trigger)")

    requested_slug = str(ctx.input_payload.get("slug") or "").strip() or None
    force = bool(ctx.input_payload.get("force"))
    if force and not getattr(ctx.user, "is_staff", False):
        if not requested_slug:
            raise AssistantActionError("force requires an explicit slug for non-admin users")
        existing_access = _get_skill_access(requested_slug)
        try:
            existing_skill = get_skill(requested_slug)
        except SkillNotFoundError:
            existing_skill = None
        if existing_skill is not None and not _can_edit_skill(ctx.user, existing_access):
            raise AssistantActionError("You can overwrite only your own skills", status=403)

    runtime_policy = ctx.input_payload.get("runtime_policy")
    if runtime_policy not in (None, "") and not isinstance(runtime_policy, dict):
        raise AssistantActionError("runtime_policy must be a JSON object")

    def _listish(key: str) -> list[str]:
        raw = ctx.input_payload.get(key)
        if isinstance(raw, list):
            return [str(x).strip() for x in raw if str(x).strip()]
        if isinstance(raw, str) and raw.strip():
            return [p.strip() for p in raw.split(",") if p.strip()]
        return []

    try:
        skill_dir = scaffold_skill(
            name=name,
            description=description,
            slug=requested_slug,
            service=str(ctx.input_payload.get("service") or "").strip(),
            category=str(ctx.input_payload.get("category") or "").strip(),
            safety_level=str(ctx.input_payload.get("safety_level") or "standard").strip() or "standard",
            ui_hint=str(ctx.input_payload.get("ui_hint") or "").strip(),
            tags=_listish("tags"),
            guardrail_summary=_listish("guardrail_summary"),
            recommended_tools=_listish("recommended_tools"),
            runtime_policy=dict(runtime_policy or {}),
            with_scripts=bool(ctx.input_payload.get("with_scripts")),
            with_references=bool(ctx.input_payload.get("with_references")),
            with_assets=bool(ctx.input_payload.get("with_assets")),
            force=force,
        )
    except (ValueError, FileExistsError) as exc:
        raise AssistantActionError(str(exc)) from exc

    validation = validate_skill_dir(skill_dir)
    if validation.errors:
        import shutil

        shutil.rmtree(skill_dir, ignore_errors=True)
        raise AssistantActionError(
            "Skill scaffold did not pass validation: " + "; ".join(validation.errors),
            details=validation.to_dict(),
        )

    # Optional body override (full SKILL body after frontmatter)
    body = str(ctx.input_payload.get("content") or ctx.input_payload.get("body") or "").strip()
    if body:
        skill_file = skill_dir / "SKILL.md"
        raw = skill_file.read_text(encoding="utf-8")
        if raw.startswith("---"):
            parts = raw.split("---", 2)
            if len(parts) >= 3:
                front = "---" + parts[1] + "---"
                skill_file.write_text(front + "\n" + body.strip() + "\n", encoding="utf-8")
                revalidation = validate_skill_dir(skill_dir)
                if revalidation.errors:
                    skill_file.write_text(raw, encoding="utf-8")
                    raise AssistantActionError(
                        "Skill content invalid: " + "; ".join(revalidation.errors),
                        details=revalidation.to_dict(),
                    )

    try:
        skill = get_skill(skill_dir.name)
    except SkillNotFoundError as exc:
        raise AssistantActionError("Skill was created but could not be loaded", status=500) from exc
    access = _ensure_skill_access(skill.slug, owner=ctx.user)
    return {
        "ok": True,
        "skill": _skill_to_detail_dict(skill, ctx.user, access),
        "validation": validation.to_dict(),
        "target_url": f"/studio/skills/{skill.slug}",
    }


def update_studio_skill(ctx: AssistantActionContext) -> dict[str, Any]:
    slug = str(ctx.input_payload.get("slug") or "").strip()
    if not slug:
        raise AssistantActionError("slug is required")
    try:
        skill = get_skill(slug)
    except SkillNotFoundError as exc:
        raise AssistantActionError("Skill not found", status=404) from exc
    access = _get_skill_access(skill.slug)
    if not _can_edit_skill(ctx.user, access):
        raise AssistantActionError("You can edit only your own skills", status=403)

    data = dict(ctx.input_payload or {})
    updated = False
    if _has_skill_metadata_update(data):
        skill, error = _update_skill_metadata_file(skill, data)
        if error:
            raise AssistantActionError(error)
        updated = True

    body = data.get("content")
    if body is None:
        body = data.get("body")
    if body is not None:
        body_text = str(body)
        skill_file = _skill_dir_from_slug(skill.slug) / "SKILL.md"
        original = skill_file.read_text(encoding="utf-8")
        # Preserve frontmatter; replace body only
        if original.startswith("---"):
            parts = original.split("---", 2)
            if len(parts) >= 3:
                meta = dict(skill.metadata or {})
                # Prefer re-render from current skill metadata if available
                try:
                    front = _render_skill_metadata(meta) if meta else ("---" + parts[1] + "---")
                except Exception:
                    front = "---" + parts[1] + "---"
                next_content = f"{front}\n{body_text.rstrip()}\n"
            else:
                next_content = body_text
        else:
            next_content = body_text
        skill_file.write_text(next_content, encoding="utf-8")
        validation = validate_skill_dir(skill_file.parent)
        if validation.errors:
            skill_file.write_text(original, encoding="utf-8")
            raise AssistantActionError(
                "Skill content invalid: " + "; ".join(validation.errors),
                details=validation.to_dict(),
            )
        try:
            skill = get_skill(skill.slug)
        except SkillNotFoundError as exc:
            skill_file.write_text(original, encoding="utf-8")
            raise AssistantActionError("Skill updated but could not be reloaded") from exc
        updated = True

    if not updated:
        raise AssistantActionError(
            "Nothing to update — pass name/description/content (or other metadata fields)"
        )

    access = _get_skill_access(skill.slug)
    return {
        "ok": True,
        "skill": _skill_to_detail_dict(skill, ctx.user, access),
        "target_url": f"/studio/skills/{skill.slug}",
    }


def build_assistant_runtime_context(user) -> dict[str, Any]:
    context: dict[str, Any] = {"pipelines": []}
    if not feature_allowed_for_user(user, "studio_pipelines"):
        return context
    pipelines = list(_pipeline_queryset_for_user(user).order_by("-updated_at", "-id")[:25])
    context["pipelines"] = [
        {
            "id": pipeline.id,
            "name": pipeline.name,
            "description": (pipeline.description or "")[:400],
            "node_count": len(pipeline.nodes or []),
            "tag_count": len(pipeline.tags or []),
            "is_template": bool(pipeline.is_template),
        }
        for pipeline in pipelines
    ]
    return context
