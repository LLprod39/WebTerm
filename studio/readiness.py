from __future__ import annotations

from collections import Counter
from typing import Any

from app.background_workers import STUDIO_WORKER_SPECS
from app.worker_state import serialize_background_worker_state
from core_ui.projects import active_project_for_user
from plugin_marketplace.services.install_service import enabled_plugin_ids_for_user
from studio import readiness_issues as ri
from studio.models import Pipeline, PipelineTrigger
from studio.node_manifest import node_manifest_payload
from studio.pipeline.pipeline_branch_scope import entry_branch_node_ids
from studio.pipeline.pipeline_runtime_context import get_pipeline_runtime_context_fields, validate_pipeline_entry_branch
from studio.pipeline.pipeline_validation import validate_pipeline_definition
from studio.readiness_requirements import integration_requirements as build_integration_requirements

_MONITORING_CONTEXT_FIELDS = {
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


def _is_admin(user) -> bool:
    return bool(user and getattr(user, "is_authenticated", False) and getattr(user, "is_staff", False))


def _pipeline_queryset_for_user(user, *, pipeline_ids: list[int] | None = None, active_only: bool = False):
    qs = Pipeline.objects.select_related("owner").prefetch_related("triggers")
    project = active_project_for_user(user)
    scoped = qs.filter(project=project) if project else qs.none()
    if not _is_admin(user):
        scoped = scoped.filter(owner=user)
    if pipeline_ids:
        scoped = scoped.filter(id__in=pipeline_ids)
    if active_only:
        scoped = scoped.filter(triggers__is_active=True).distinct()
    return scoped.order_by("-updated_at", "-id")


def _node_types(nodes: Any) -> set[str]:
    return (
        {str(node.get("type") or "") for node in nodes if isinstance(node, dict)} if isinstance(nodes, list) else set()
    )


def _node_data(node: dict[str, Any]) -> dict[str, Any]:
    return node.get("data") if isinstance(node.get("data"), dict) else {}


def _node_by_id(nodes: Any, node_id: str) -> dict[str, Any] | None:
    if not isinstance(nodes, list):
        return None
    for node in nodes:
        if isinstance(node, dict) and str(node.get("id") or "") == node_id:
            return node
    return None


def _trigger_worker(trigger_type: str) -> str | None:
    if trigger_type == PipelineTrigger.TYPE_SCHEDULE:
        return "scheduled-pipelines"
    if trigger_type == PipelineTrigger.TYPE_MONITORING:
        return "monitor"
    return None


def _trigger_supplied_context_fields(pipeline: Pipeline, trigger: PipelineTrigger) -> set[str]:
    trigger_type = str(trigger.trigger_type or "")
    if trigger_type == PipelineTrigger.TYPE_MONITORING:
        return set(_MONITORING_CONTEXT_FIELDS)
    if trigger_type == PipelineTrigger.TYPE_WEBHOOK:
        node = _node_by_id(pipeline.nodes, trigger.node_id)
        node_data = _node_data(node or {})
        payload_map = trigger.webhook_payload_map if isinstance(trigger.webhook_payload_map, dict) else {}
        if not payload_map and isinstance(node_data.get("webhook_payload_map"), dict):
            payload_map = node_data["webhook_payload_map"]
        return {str(key) for key in payload_map if str(key).strip()}
    return set()


def _trigger_payload(pipeline: Pipeline, trigger: PipelineTrigger) -> dict[str, Any]:
    branch_errors = validate_pipeline_entry_branch(pipeline.nodes, pipeline.edges, trigger.node_id)
    context_fields = get_pipeline_runtime_context_fields(
        pipeline.nodes,
        edges=pipeline.edges,
        entry_node_id=trigger.node_id,
    )
    supplied_context_fields = _trigger_supplied_context_fields(pipeline, trigger)
    unresolved_context_fields = [field for field in context_fields if field not in supplied_context_fields]
    worker = _trigger_worker(trigger.trigger_type)
    payload: dict[str, Any] = {
        "id": trigger.pk,
        "node_id": trigger.node_id,
        "name": trigger.name,
        "type": trigger.trigger_type,
        "is_active": trigger.is_active,
        "required_context_fields": context_fields,
        "supplied_context_fields": sorted(supplied_context_fields & set(context_fields)),
        "unresolved_context_fields": unresolved_context_fields,
        "errors": branch_errors,
        "issues": ri.validation_issues(branch_errors),
    }
    context_issue = ri.runtime_context_issue(payload)
    if context_issue:
        payload["issues"].append(context_issue)
    if worker:
        payload["worker"] = worker
    return payload


def _pipeline_payload(pipeline: Pipeline, *, entry_node_id: str = "") -> dict[str, Any]:
    graph_errors = validate_pipeline_definition(
        nodes=pipeline.nodes,
        edges=pipeline.edges,
        owner=pipeline.owner,
        graph_version=pipeline.graph_version,
    )
    active_triggers = [trigger for trigger in pipeline.triggers.all() if trigger.is_active]
    entry = str(entry_node_id or "").strip()
    entry_errors = []
    if entry:
        active_triggers = [trigger for trigger in active_triggers if trigger.node_id == entry]
        if not active_triggers:
            entry_errors.append(f"Entry trigger '{entry}' was not found or is inactive.")
    branch_node_ids = entry_branch_node_ids(pipeline, entry) if entry else None
    integration_requirements = build_integration_requirements(pipeline, node_ids=branch_node_ids)
    integration_issues = []
    for item in integration_requirements:
        issue = ri.integration_issue(item)
        if issue:
            item["issue"] = issue
            integration_issues.append(issue)
    integration_errors = [item["message"] for item in integration_requirements if item["severity"] == "error"]
    integration_warnings = [item["message"] for item in integration_requirements if item["severity"] == "warning"]
    trigger_payloads = [_trigger_payload(pipeline, trigger) for trigger in active_triggers]
    trigger_issues = [issue for trigger in trigger_payloads for issue in trigger["issues"]]
    trigger_errors = [error for trigger in trigger_payloads for error in trigger["errors"]]
    warnings = []
    if not active_triggers:
        warnings.append("Pipeline has no active triggers.")
    if any(trigger["unresolved_context_fields"] for trigger in trigger_payloads):
        warnings.append("Some triggers require runtime context before launch.")
    status = (
        "error"
        if graph_errors or entry_errors or trigger_errors or integration_errors
        else "warning"
        if warnings or integration_warnings
        else "ready"
    )
    return {
        "id": pipeline.pk,
        "name": pipeline.name,
        "status": status,
        "graph_version": pipeline.graph_version,
        "node_count": len(pipeline.nodes or []),
        "active_trigger_count": len(active_triggers),
        "errors": [*graph_errors, *entry_errors, *trigger_errors, *integration_errors],
        "warnings": [*warnings, *integration_warnings],
        "issues": [*ri.validation_issues([*graph_errors, *entry_errors]), *trigger_issues, *integration_issues],
        "integration_requirements": integration_requirements,
        "triggers": trigger_payloads,
    }


def _worker_requirements(
    pipelines: list[dict[str, Any]], raw_pipelines: list[Pipeline], *, entry_node_id: str = ""
) -> list[dict[str, Any]]:
    required = Counter()
    for pipeline in pipelines:
        for trigger in pipeline["triggers"]:
            worker = trigger.get("worker")
            if worker:
                required[worker] += 1
    for pipeline in raw_pipelines:
        node_ids = entry_branch_node_ids(pipeline, entry_node_id) if entry_node_id else None
        nodes = [node for node in (pipeline.nodes or []) if node_ids is None or str(node.get("id") or "") in node_ids]
        if "logic/telegram_input" in _node_types(nodes):
            required["telegram-bot"] += 1
    requirements = []
    for worker, count in sorted(required.items()):
        spec = STUDIO_WORKER_SPECS[worker]
        state = serialize_background_worker_state(spec["worker_kind"])
        ready = state["status"] == "running" and not state["is_stale"]
        item = {
            "worker": worker,
            "worker_kind": spec["worker_kind"],
            "required_by": count,
            "command": spec["command"],
            "ready": ready,
            "state": state,
        }
        issue = ri.worker_issue(item)
        if issue:
            item["issues"] = [issue]
        requirements.append(item)
    return requirements


def build_studio_readiness_report(
    user,
    *,
    pipeline_ids: list[int] | None = None,
    active_only: bool = False,
    entry_node_id: str = "",
) -> dict[str, Any]:
    entry = str(entry_node_id or "").strip()
    requested_pipeline_ids = list(dict.fromkeys(int(item) for item in (pipeline_ids or [])))
    raw_pipelines = list(_pipeline_queryset_for_user(user, pipeline_ids=pipeline_ids, active_only=active_only))
    found_pipeline_ids = {pipeline.id for pipeline in raw_pipelines}
    missing_pipeline_ids = [item for item in requested_pipeline_ids if item not in found_pipeline_ids]
    pipelines = [_pipeline_payload(pipeline, entry_node_id=entry) for pipeline in raw_pipelines]
    worker_requirements = _worker_requirements(pipelines, raw_pipelines, entry_node_id=entry)
    error_count = sum(1 for pipeline in pipelines if pipeline["status"] == "error")
    warning_count = sum(1 for pipeline in pipelines if pipeline["status"] == "warning")
    worker_not_ready_count = sum(1 for worker in worker_requirements if not worker["ready"])
    issues = [issue for worker in worker_requirements for issue in worker.get("issues", [])]
    issues.extend(issue for pipeline in pipelines for issue in pipeline["issues"])
    scope_issue = ri.pipeline_scope_issue(missing_pipeline_ids, active_only=active_only)
    if scope_issue:
        issues.insert(0, scope_issue)
    integration_error_count = sum(
        1 for pipeline in pipelines for item in pipeline["integration_requirements"] if item["severity"] == "error"
    )
    integration_warning_count = sum(
        1 for pipeline in pipelines for item in pipeline["integration_requirements"] if item["severity"] == "warning"
    )
    overall = (
        "not_ready"
        if error_count or worker_not_ready_count or missing_pipeline_ids
        else "warning"
        if warning_count
        else "ready"
    )
    nodes = node_manifest_payload(enabled_plugin_ids_for_user(user))
    scope = {"active_only": active_only, "pipeline_ids": requested_pipeline_ids}
    if entry:
        scope["entry_node_id"] = entry
    if missing_pipeline_ids:
        scope["missing_pipeline_ids"] = missing_pipeline_ids
    return {
        "version": 1,
        "status": overall,
        "scope": scope,
        "summary": {
            "node_type_count": len(nodes),
            "pipeline_count": len(pipelines),
            "missing_pipeline_count": len(missing_pipeline_ids),
            "pipeline_error_count": error_count,
            "pipeline_warning_count": warning_count,
            "worker_not_ready_count": worker_not_ready_count,
            "integration_error_count": integration_error_count,
            "integration_warning_count": integration_warning_count,
            "issue_count": len(issues),
            "active_trigger_count": sum(pipeline["active_trigger_count"] for pipeline in pipelines),
        },
        "issues": issues,
        "worker_requirements": worker_requirements,
        "pipelines": pipelines,
    }
