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
from studio.pipeline_preflight import pipeline_integration_diagnostics
from studio.pipeline_runtime_context import validate_pipeline_entry_branch, validate_pipeline_runtime_context
from studio.pipeline_validation import ensure_json_object, validate_pipeline_definition
from studio.readiness_issues import validation_issues
from studio.trigger_dispatch import get_pipeline_run_limit_error, pipeline_run_creation_error_details
from studio.views.common import _err, _json_body, _limit_err, _ok, _validation_err
from studio.views.pipeline_helpers import (
    _create_pipeline_run,
    _get_pipeline,
    _launch_pipeline_run,
    _pipeline_queryset_for_user,
)

STUDIO_FEATURE_PIPELINES = "studio_pipelines"
_TRIGGER_NODE_TYPES = {
    PipelineTrigger.TYPE_MANUAL: "trigger/manual",
    PipelineTrigger.TYPE_WEBHOOK: "trigger/webhook",
    PipelineTrigger.TYPE_SCHEDULE: "trigger/schedule",
    PipelineTrigger.TYPE_MONITORING: "trigger/monitoring",
}
_MONITORING_CONTEXT = {
    "alert_id",
    "alert_type",
    "alert_severity",
    "alert_title",
    "alert_message",
    "alert_metadata",
    "server_id",
    "server_name",
    "server_host",
    "server_username",
    "container_name",
    "container_names",
    "container_names_csv",
    "trigger_source",
}


def _activation_context(trigger_type: str, webhook_payload_map) -> dict:
    if trigger_type == PipelineTrigger.TYPE_WEBHOOK and isinstance(webhook_payload_map, dict):
        return {str(key): "__mapped__" for key, path in webhook_payload_map.items() if str(key).strip() and str(path).strip()}
    if trigger_type == PipelineTrigger.TYPE_MONITORING:
        return {field: "__monitoring__" for field in _MONITORING_CONTEXT}
    return {}


def _node_type_for_id(pipeline, node_id: str) -> str:
    for node in pipeline.nodes or []:
        if isinstance(node, dict) and str(node.get("id") or "").strip() == node_id:
            return str(node.get("type") or "").strip()
    return ""


def _activation_validation(pipeline, *, node_id: str, trigger_type: str, webhook_payload_map) -> tuple[list[str], list[dict]]:
    errors = validate_pipeline_definition(
        nodes=pipeline.nodes,
        edges=pipeline.edges,
        owner=pipeline.owner,
        graph_version=pipeline.graph_version,
    )
    issues = validation_issues(errors)
    expected_node_type = _TRIGGER_NODE_TYPES.get(trigger_type)
    actual_node_type = _node_type_for_id(pipeline, node_id)
    if expected_node_type and actual_node_type and actual_node_type != expected_node_type:
        message = f"Trigger node '{node_id}' type {actual_node_type} does not match trigger_type '{trigger_type}'."
        errors.append(message)
        issues.extend(validation_issues([message]))
    if errors:
        return errors, issues

    branch_errors = validate_pipeline_entry_branch(pipeline.nodes, pipeline.edges, node_id)
    errors.extend(branch_errors)
    issues.extend(validation_issues(branch_errors))
    if trigger_type != PipelineTrigger.TYPE_MANUAL:
        context_errors = validate_pipeline_runtime_context(
            pipeline.nodes,
            _activation_context(trigger_type, webhook_payload_map),
            edges=pipeline.edges,
            entry_node_id=node_id,
        )
        errors.extend(context_errors)
        issues.extend(validation_issues(context_errors))

    integration = pipeline_integration_diagnostics(pipeline, entry_node_id=node_id)
    errors.extend(integration["errors"])
    issues.extend(integration["issues"])
    return errors, issues


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
        if trigger_defaults["is_active"]:
            errors, issues = _activation_validation(
                pipeline,
                node_id=node_id,
                trigger_type=trigger_defaults["trigger_type"],
                webhook_payload_map=trigger_defaults["webhook_payload_map"],
            )
            if errors:
                return _validation_err(errors, prefix="Trigger cannot be activated", issues=issues)
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
        next_trigger_type = data.get("trigger_type", trigger.trigger_type)
        next_is_active = data.get("is_active", trigger.is_active)
        next_payload_map = data.get("webhook_payload_map", trigger.webhook_payload_map)
        if next_is_active:
            errors, issues = _activation_validation(
                trigger.pipeline,
                node_id=next_node_id,
                trigger_type=next_trigger_type,
                webhook_payload_map=next_payload_map,
            )
            if errors:
                return _validation_err(errors, prefix="Trigger cannot be activated", issues=issues)
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

    branch_errors = validate_pipeline_entry_branch(
        trigger.pipeline.nodes,
        trigger.pipeline.edges,
        trigger.node_id,
    )
    if branch_errors:
        return _validation_err(branch_errors, prefix="Pipeline is not runnable")

    context = _map_payload(payload, trigger.webhook_payload_map)
    context_errors = validate_pipeline_runtime_context(
        trigger.pipeline.nodes,
        context,
        edges=trigger.pipeline.edges,
        entry_node_id=trigger.node_id,
    )
    if context_errors:
        return _validation_err(context_errors, prefix="Pipeline is not runnable")

    integration = pipeline_integration_diagnostics(trigger.pipeline, entry_node_id=trigger.node_id)
    if integration["errors"]:
        return _validation_err(
            integration["errors"],
            prefix="Pipeline is not runnable",
            issues=integration["issues"],
        )

    limit_error = get_pipeline_run_limit_error(trigger.pipeline.owner)
    if limit_error:
        return _limit_err(limit_error)

    try:
        run = _create_pipeline_run(
            pipeline=trigger.pipeline,
            trigger=trigger,
            context=context,
            trigger_data=payload,
            entry_node_id=trigger.node_id,
        )
    except ValueError as exc:
        return _validation_err(pipeline_run_creation_error_details(exc), prefix="Pipeline is not runnable")
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
