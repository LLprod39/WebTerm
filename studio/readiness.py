from __future__ import annotations

import os
from collections import Counter
from typing import Any

from app.background_workers import STUDIO_WORKER_SPECS
from app.core.model_utils import resolve_provider_and_model
from app.worker_state import serialize_background_worker_state
from django.conf import settings
from studio.models import AgentConfig, MCPServerPool, Pipeline, PipelineTrigger
from studio.node_manifest import node_manifest_payload
from studio.pipeline_branch_scope import entry_branch_node_ids
from studio.pipeline_notifications import _load_notif_cfg
from studio.pipeline_runtime_context import get_pipeline_runtime_context_fields, validate_pipeline_entry_branch
from studio.pipeline_validation import validate_pipeline_definition
from studio import readiness_issues as ri

_LLM_PROVIDER_KEYS = {
    "gemini": ("GEMINI_API_KEY",),
    "openai": ("OPENAI_API_KEY", "CODEX_API_KEY"),
    "fair": ("FAIR_HYPERION_API_KEY", "FAIR_API_KEY"),
    "grok": ("GROK_API_KEY",),
    "claude": ("ANTHROPIC_API_KEY",),
    "ollama": ("OLLAMA_API_KEY",),
}
_SEVERITY_RANK = {"ready": 0, "warning": 1, "error": 2}
_MONITORING_CONTEXT_FIELDS = set(
    "alert_id alert_type alert_severity alert_title alert_message alert_metadata server_id server_name "
    "server_host server_username container_name container_names container_names_csv trigger_source".split()
)


def _is_admin(user) -> bool:
    return bool(user and getattr(user, "is_authenticated", False) and getattr(user, "is_staff", False))


def _pipeline_queryset_for_user(user, *, pipeline_ids: list[int] | None = None, active_only: bool = False):
    qs = Pipeline.objects.select_related("owner").prefetch_related("triggers")
    scoped = qs if _is_admin(user) else qs.filter(owner=user)
    if pipeline_ids:
        scoped = scoped.filter(id__in=pipeline_ids)
    if active_only:
        scoped = scoped.filter(triggers__is_active=True).distinct()
    return scoped.order_by("-updated_at", "-id")


def _node_types(nodes: Any) -> set[str]:
    return {str(node.get("type") or "") for node in nodes if isinstance(node, dict)} if isinstance(nodes, list) else set()


def _node_data(node: dict[str, Any]) -> dict[str, Any]: return node.get("data") if isinstance(node.get("data"), dict) else {}


def _node_by_id(nodes: Any, node_id: str) -> dict[str, Any] | None:
    if not isinstance(nodes, list):
        return None
    for node in nodes:
        if isinstance(node, dict) and str(node.get("id") or "") == node_id:
            return node
    return None


def _has_value(value: Any) -> bool: return bool(str(value or "").strip())


def _first_nonblank(*values: Any) -> Any:
    for value in values:
        if _has_value(value):
            return value
    return ""


def _env_any(keys: tuple[str, ...]) -> bool: return any(_has_value(os.getenv(key)) for key in keys)


def _managed_llm_key(provider: str) -> bool:
    try:
        from core_ui.managed_secrets import has_llm_api_key

        return has_llm_api_key(provider)
    except Exception:
        return False


def _llm_provider_ready(provider: str) -> bool:
    if provider == "auto":
        return any(_llm_provider_ready(item) for item in ("fair", "gemini", "openai", "grok", "claude", "ollama"))
    if provider == "ollama":
        return (
            _has_value(os.getenv("OLLAMA_BASE_URL"))
            or _has_value(getattr(settings, "OLLAMA_BASE_URL", ""))
            or _managed_llm_key("ollama")
            or _env_any(_LLM_PROVIDER_KEYS["ollama"])
        )
    keys = _LLM_PROVIDER_KEYS.get(provider)
    return bool(keys and (_env_any(keys) or _managed_llm_key(provider)))


def _email_backend_needs_smtp() -> bool:
    return "smtp" in str(getattr(settings, "EMAIL_BACKEND", "") or "").lower() or not getattr(settings, "EMAIL_BACKEND", "")


def _upsert_requirement(
    requirements: dict[str, dict[str, Any]],
    key: str,
    *,
    kind: str,
    name: str,
    node_id: str,
    status: str,
    severity: str,
    message: str,
) -> None:
    current = requirements.setdefault(
        key,
        {
            "kind": kind,
            "name": name,
            "status": status,
            "severity": severity,
            "required_by_node_ids": [],
            "message": message,
        },
    )
    if node_id and node_id not in current["required_by_node_ids"]:
        current["required_by_node_ids"].append(node_id)
    if _SEVERITY_RANK[severity] > _SEVERITY_RANK[current["severity"]]:
        current["status"] = status
        current["severity"] = severity
        current["message"] = message


def _telegram_requirement(requirements: dict[str, dict[str, Any]], node_id: str, data: dict[str, Any]) -> None:
    cfg = _load_notif_cfg()
    token = _first_nonblank(
        data.get("bot_token"),
        data.get("tg_bot_token"),
        data.get("telegram_bot_token"),
        cfg.get("telegram_bot_token"),
    )
    chat = _first_nonblank(
        data.get("chat_id"),
        data.get("tg_chat_id"),
        data.get("telegram_chat_id"),
        cfg.get("telegram_chat_id"),
    )
    if not _has_value(token):
        _upsert_requirement(
            requirements,
            "telegram:bot-token",
            kind="telegram",
            name="Telegram bot token",
            node_id=node_id,
            status="missing",
            severity="error",
            message="Set TELEGRAM_BOT_TOKEN or a node-level bot_token.",
        )
    else:
        _upsert_requirement(
            requirements,
            "telegram:bot-token",
            kind="telegram",
            name="Telegram bot token",
            node_id=node_id,
            status="ready",
            severity="ready",
            message="Telegram bot token is configured.",
        )
    if not _has_value(chat):
        _upsert_requirement(
            requirements,
            "telegram:chat",
            kind="telegram",
            name="Telegram chat",
            node_id=node_id,
            status="runtime_context_or_missing",
            severity="warning",
            message="Set TELEGRAM_CHAT_ID/node chat_id, or provide tg_chat_id/chat_id in runtime context.",
        )
    else:
        _upsert_requirement(
            requirements,
            "telegram:chat",
            kind="telegram",
            name="Telegram chat",
            node_id=node_id,
            status="ready",
            severity="ready",
            message="Telegram chat is configured.",
        )


def _email_requirement(requirements: dict[str, dict[str, Any]], node_id: str, data: dict[str, Any]) -> None:
    cfg = _load_notif_cfg()
    recipient = _first_nonblank(data.get("to_email"), cfg.get("notify_email"))
    smtp_host = _first_nonblank(data.get("smtp_host"), cfg.get("smtp_host"), getattr(settings, "EMAIL_HOST", ""))
    if not _has_value(recipient):
        _upsert_requirement(
            requirements,
            "email:recipient",
            kind="email",
            name="Email recipient",
            node_id=node_id,
            status="missing",
            severity="error",
            message="Set PIPELINE_NOTIFY_EMAIL or node to_email.",
        )
    else:
        _upsert_requirement(
            requirements,
            "email:recipient",
            kind="email",
            name="Email recipient",
            node_id=node_id,
            status="ready",
            severity="ready",
            message="Email recipient is configured.",
        )
    if _email_backend_needs_smtp() and not _has_value(smtp_host):
        _upsert_requirement(
            requirements,
            "email:smtp",
            kind="email",
            name="SMTP host",
            node_id=node_id,
            status="missing",
            severity="warning",
            message="Set EMAIL_HOST or node smtp_host for real SMTP delivery.",
        )


def _llm_requirement(requirements: dict[str, dict[str, Any]], node_id: str, data: dict[str, Any]) -> None:
    provider, _model = resolve_provider_and_model(data.get("provider"), data.get("model"), default_provider="gemini")
    ready = _llm_provider_ready(provider)
    key = f"llm:{provider}"
    _upsert_requirement(
        requirements,
        key,
        kind="llm",
        name=f"LLM provider: {provider}",
        node_id=node_id,
        status="ready" if ready else "missing",
        severity="ready" if ready else "error",
        message=(f"LLM provider {provider} is configured." if ready else f"Configure credentials/runtime for LLM provider {provider}."),
    )


def _mcp_requirement(requirements: dict[str, dict[str, Any]], node_id: str, mcp: MCPServerPool | None) -> None:
    if mcp is None:
        _upsert_requirement(
            requirements,
            f"mcp:missing:{node_id}",
            kind="mcp",
            name="MCP server",
            node_id=node_id,
            status="missing",
            severity="error",
            message="Select an accessible MCP server.",
        )
        return
    key = f"mcp:{mcp.pk}"
    if mcp.last_test_ok is False:
        status, severity, message = "failed", "error", "MCP server last connection test failed."
    elif mcp.last_test_ok is None:
        status, severity, message = "untested", "warning", "MCP server has not been connection-tested yet."
    else:
        status, severity, message = "ready", "ready", "MCP server last connection test passed."
    _upsert_requirement(
        requirements,
        key,
        kind="mcp",
        name=f"MCP server: {mcp.name}",
        node_id=node_id,
        status=status,
        severity=severity,
        message=message,
    )


def _integration_requirements(pipeline: Pipeline, *, node_ids: set[str] | None = None) -> list[dict[str, Any]]:
    requirements: dict[str, dict[str, Any]] = {}
    for node in pipeline.nodes or []:
        if not isinstance(node, dict):
            continue
        node_id = str(node.get("id") or "").strip()
        if node_ids is not None and node_id not in node_ids:
            continue
        node_type = str(node.get("type") or "").strip()
        data = _node_data(node)
        if node_type in {"output/telegram", "logic/telegram_input"}:
            _telegram_requirement(requirements, node_id, data)
        elif node_type == "output/email":
            _email_requirement(requirements, node_id, data)
        elif node_type in {"agent/llm_query", "agent/react", "agent/multi"}:
            _llm_requirement(requirements, node_id, data)
            agent_config_id = data.get("agent_config_id")
            if agent_config_id not in (None, ""):
                agent_config = AgentConfig.objects.filter(owner=pipeline.owner, id=agent_config_id).first()
                if agent_config:
                    _llm_requirement(requirements, node_id, {"model": agent_config.model})
                    for mcp in agent_config.mcp_servers.all():
                        _mcp_requirement(requirements, node_id, mcp)
        if node_type == "agent/mcp_call":
            mcp_server = None
            with_id = data.get("mcp_server_id")
            if with_id not in (None, ""):
                mcp_server = MCPServerPool.objects.filter(owner=pipeline.owner, id=with_id).first()
            _mcp_requirement(requirements, node_id, mcp_server)
        elif node_type in {"agent/react", "agent/multi"}:
            for raw_id in data.get("mcp_server_ids") or []:
                mcp = MCPServerPool.objects.filter(owner=pipeline.owner, id=raw_id).first()
                _mcp_requirement(requirements, node_id, mcp)
    return sorted(requirements.values(), key=lambda item: (item["kind"], item["name"]))


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
    integration_requirements = _integration_requirements(pipeline, node_ids=branch_node_ids)
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


def _worker_requirements(pipelines: list[dict[str, Any]], raw_pipelines: list[Pipeline], *, entry_node_id: str = "") -> list[dict[str, Any]]:
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
        1
        for pipeline in pipelines
        for item in pipeline["integration_requirements"]
        if item["severity"] == "error"
    )
    integration_warning_count = sum(
        1
        for pipeline in pipelines
        for item in pipeline["integration_requirements"]
        if item["severity"] == "warning"
    )
    overall = "not_ready" if error_count or worker_not_ready_count or missing_pipeline_ids else "warning" if warning_count else "ready"
    nodes = node_manifest_payload()
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
