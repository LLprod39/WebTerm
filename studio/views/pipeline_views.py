"""
Studio pipeline CRUD and run endpoints.
"""

from django.http import JsonResponse
from django.views.decorators.http import require_http_methods

from core_ui.decorators import require_feature
from studio.models import CURRENT_PIPELINE_GRAPH_VERSION, Pipeline, PipelineTrigger
from studio.pipeline_validation import ensure_json_object, validate_pipeline_definition
from studio.trigger_dispatch import get_pipeline_run_limit_error
from studio.views.common import _err, _json_body, _ok, _validation_err
from studio.views.pipeline_helpers import (
    _create_pipeline_run,
    _default_pipeline_draft_nodes,
    _get_pipeline,
    _launch_pipeline_run,
    _pipeline_queryset_for_user,
    _resolve_manual_entry_trigger,
)

STUDIO_FEATURE_PIPELINES = "studio_pipelines"


@require_feature(STUDIO_FEATURE_PIPELINES)
def api_pipelines(request):
    if request.method == "GET":
        qs = _pipeline_queryset_for_user(request.user)
        search = request.GET.get("q", "").strip()
        if search:
            qs = qs.filter(name__icontains=search)
        return _ok([pipeline.to_list_dict() for pipeline in qs])

    if request.method == "POST":
        data = _json_body(request)
        name = data.get("name", "").strip()
        if not name:
            return _err("name is required")
        nodes = data.get("nodes", [])
        edges = data.get("edges", [])
        if not nodes and not edges:
            nodes = _default_pipeline_draft_nodes()
        errors = validate_pipeline_definition(
            nodes=nodes,
            edges=edges,
            owner=request.user,
            graph_version=CURRENT_PIPELINE_GRAPH_VERSION,
        )
        if errors:
            return _validation_err(errors, prefix="Pipeline validation failed")
        pipeline = Pipeline.objects.create(
            name=name,
            description=data.get("description", ""),
            icon=data.get("icon", "⚡"),
            tags=data.get("tags", []),
            nodes=nodes,
            edges=edges,
            graph_version=CURRENT_PIPELINE_GRAPH_VERSION,
            owner=request.user,
        )
        pipeline.sync_triggers_from_nodes()
        return _ok(pipeline.to_detail_dict(), status=201)

    return _err("Method not allowed", 405)


@require_feature(STUDIO_FEATURE_PIPELINES)
def api_pipeline_detail(request, pipeline_id: int):
    pipeline = _get_pipeline(request, pipeline_id)
    if pipeline is None:
        return _err("Pipeline not found", 404)

    if request.method == "GET":
        return _ok(pipeline.to_detail_dict())

    if request.method == "PUT":
        data = _json_body(request)
        next_nodes = data.get("nodes", pipeline.nodes)
        next_edges = data.get("edges", pipeline.edges)
        errors = validate_pipeline_definition(
            nodes=next_nodes,
            edges=next_edges,
            owner=pipeline.owner,
            graph_version=CURRENT_PIPELINE_GRAPH_VERSION,
        )
        if errors:
            return _validation_err(errors, prefix="Pipeline validation failed")
        for field in ("name", "description", "icon", "tags", "nodes", "edges", "is_shared"):
            if field in data:
                setattr(pipeline, field, data[field])
        pipeline.graph_version = CURRENT_PIPELINE_GRAPH_VERSION
        pipeline.save()
        pipeline.sync_triggers_from_nodes()
        return _ok(pipeline.to_detail_dict())

    if request.method == "DELETE":
        pipeline.delete()
        return JsonResponse({"ok": True})

    return _err("Method not allowed", 405)


@require_feature(STUDIO_FEATURE_PIPELINES)
@require_http_methods(["POST"])
def api_pipeline_run(request, pipeline_id: int):
    pipeline = _get_pipeline(request, pipeline_id)
    if pipeline is None:
        return _err("Pipeline not found", 404)

    limit_error = get_pipeline_run_limit_error(pipeline.owner)
    if limit_error:
        return JsonResponse(limit_error, status=429)

    payload = _json_body(request)
    context, error = ensure_json_object(payload.get("context", {}), label="context")
    if error:
        return _err(error)
    entry_node_id = str(payload.get("entry_node_id") or "").strip()

    validation_errors = validate_pipeline_definition(
        nodes=pipeline.nodes,
        edges=pipeline.edges,
        owner=pipeline.owner,
        graph_version=pipeline.graph_version,
        require_manual_trigger=True,
    )
    if validation_errors:
        return _validation_err(validation_errors, prefix="Pipeline is not runnable")
    selected_trigger, trigger_errors = _resolve_manual_entry_trigger(pipeline, entry_node_id)
    if trigger_errors:
        return _validation_err(trigger_errors, prefix="Pipeline is not runnable")

    run = _create_pipeline_run(
        pipeline=pipeline,
        triggered_by=request.user,
        trigger=selected_trigger,
        context=context,
        trigger_data={
            "source": "manual",
            "trigger_type": PipelineTrigger.TYPE_MANUAL,
            "entry_node_id": selected_trigger.node_id,
        },
        entry_node_id=selected_trigger.node_id,
    )
    _launch_pipeline_run(run)
    return _ok(run.to_dict(), status=202)


@require_feature(STUDIO_FEATURE_PIPELINES)
@require_http_methods(["POST"])
def api_pipeline_clone(request, pipeline_id: int):
    pipeline = _get_pipeline(request, pipeline_id)
    if pipeline is None:
        return _err("Pipeline not found", 404)

    clone = Pipeline.objects.create(
        name=f"{pipeline.name} (copy)",
        description=pipeline.description,
        icon=pipeline.icon,
        tags=pipeline.tags,
        nodes=pipeline.nodes,
        edges=pipeline.edges,
        graph_version=CURRENT_PIPELINE_GRAPH_VERSION,
        owner=request.user,
    )
    clone.sync_triggers_from_nodes()
    return _ok(clone.to_detail_dict(), status=201)


@require_feature(STUDIO_FEATURE_PIPELINES)
def api_pipeline_runs(request, pipeline_id: int):
    pipeline = _get_pipeline(request, pipeline_id)
    if pipeline is None:
        return _err("Pipeline not found", 404)
    runs = pipeline.runs.order_by("-created_at")[:50]
    return _ok([run.to_dict() for run in runs])
