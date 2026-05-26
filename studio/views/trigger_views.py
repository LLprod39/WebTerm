"""
Studio pipeline trigger endpoints.
"""

import json

from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from core_ui.decorators import require_feature
from studio.models import PipelineTrigger
from studio.pipeline_validation import ensure_json_object, validate_pipeline_definition
from studio.trigger_dispatch import get_pipeline_run_limit_error
from studio.views.common import _err, _json_body, _ok, _validation_err
from studio.views.pipeline_helpers import (
    _create_pipeline_run,
    _get_pipeline,
    _launch_pipeline_run,
    _pipeline_queryset_for_user,
)

STUDIO_FEATURE_PIPELINES = "studio_pipelines"


@require_feature(STUDIO_FEATURE_PIPELINES)
def api_triggers(request):
    if request.method == "GET":
        pipeline_id = request.GET.get("pipeline_id")
        qs = PipelineTrigger.objects.filter(pipeline__in=_pipeline_queryset_for_user(request.user))
        if pipeline_id:
            qs = qs.filter(pipeline_id=pipeline_id)
        return _ok([trigger.to_dict() for trigger in qs])

    if request.method == "POST":
        data = _json_body(request)
        pipeline_id = data.get("pipeline_id")
        if not pipeline_id:
            return _err("pipeline_id is required")
        pipeline = _get_pipeline(request, int(pipeline_id))
        if pipeline is None:
            return _err("Pipeline not found", 404)
        node_id = str(data.get("node_id", "") or "").strip()
        trigger_defaults = {
            "name": data.get("name", ""),
            "trigger_type": data.get("trigger_type", PipelineTrigger.TYPE_MANUAL),
            "is_active": data.get("is_active", True),
            "cron_expression": data.get("cron_expression", ""),
            "webhook_payload_map": data.get("webhook_payload_map", {}),
            "monitoring_filters": data.get("monitoring_filters", {}),
        }
        if node_id:
            trigger, _created = PipelineTrigger.objects.update_or_create(
                pipeline=pipeline,
                node_id=node_id,
                defaults=trigger_defaults,
            )
        else:
            trigger = PipelineTrigger.objects.create(
                pipeline=pipeline,
                node_id=node_id,
                **trigger_defaults,
            )
        return _ok(trigger.to_dict(), status=201)

    return _err("Method not allowed", 405)


@require_feature(STUDIO_FEATURE_PIPELINES)
def api_trigger_detail(request, trigger_id: int):
    try:
        trigger = PipelineTrigger.objects.get(pk=trigger_id, pipeline__in=_pipeline_queryset_for_user(request.user))
    except PipelineTrigger.DoesNotExist:
        return _err("Trigger not found", 404)

    if request.method == "PUT":
        data = _json_body(request)
        next_node_id = str(data.get("node_id", trigger.node_id) or "").strip()
        if (
            next_node_id
            and next_node_id != trigger.node_id
            and PipelineTrigger.objects.filter(pipeline=trigger.pipeline, node_id=next_node_id).exclude(pk=trigger.pk).exists()
        ):
            return _err(f"Trigger for node '{next_node_id}' already exists")
        for field in (
            "node_id",
            "name",
            "trigger_type",
            "is_active",
            "cron_expression",
            "webhook_payload_map",
            "monitoring_filters",
        ):
            if field in data:
                setattr(trigger, field, data[field])
        trigger.save()
        return _ok(trigger.to_dict())

    if request.method == "DELETE":
        trigger.delete()
        return JsonResponse({"ok": True})

    return _err("Method not allowed", 405)


@csrf_exempt
@require_http_methods(["POST"])
def api_trigger_receive(request, token: str):
    """Public webhook endpoint authenticated by token in URL."""
    try:
        trigger = PipelineTrigger.objects.select_related("pipeline").get(
            webhook_token=token,
            trigger_type=PipelineTrigger.TYPE_WEBHOOK,
            is_active=True,
        )
    except PipelineTrigger.DoesNotExist:
        return _err("Invalid token", 404)

    body = request.body.strip()
    if not body:
        payload = {}
    else:
        try:
            payload = json.loads(body)
        except (json.JSONDecodeError, UnicodeDecodeError):
            return _err("Webhook payload must be valid JSON")

    payload, error = ensure_json_object(payload, label="Webhook payload")
    if error:
        return _err(error)

    validation_errors = validate_pipeline_definition(
        nodes=trigger.pipeline.nodes,
        edges=trigger.pipeline.edges,
        owner=trigger.pipeline.owner,
        graph_version=trigger.pipeline.graph_version,
    )
    if validation_errors:
        return _validation_err(validation_errors, prefix="Pipeline is not runnable")

    context = _map_payload(payload, trigger.webhook_payload_map)

    limit_error = get_pipeline_run_limit_error(trigger.pipeline.owner)
    if limit_error:
        return JsonResponse(limit_error, status=429)

    run = _create_pipeline_run(
        pipeline=trigger.pipeline,
        trigger=trigger,
        context=context,
        trigger_data=payload,
        entry_node_id=trigger.node_id,
    )
    trigger.last_triggered_at = timezone.now()
    trigger.save(update_fields=["last_triggered_at"])

    _launch_pipeline_run(run)
    return _ok({"ok": True, "run_id": run.pk})


def _map_payload(payload: dict, mapping: dict) -> dict:
    """Map incoming webhook payload to pipeline context variables."""
    if not isinstance(payload, dict):
        return {}
    if not isinstance(mapping, dict):
        return dict(payload)
    if not mapping:
        return dict(payload)
    context = {}
    for context_key, payload_path in mapping.items():
        value = payload
        for path_part in payload_path.split("."):
            if isinstance(value, dict):
                value = value.get(path_part)
            else:
                value = None
                break
        context[context_key] = value
    return context
