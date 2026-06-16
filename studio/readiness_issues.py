from __future__ import annotations

import re
from typing import Any

_NODE_ID_RE = re.compile(r"(?:Node|node|Trigger node|Entry node|Selected trigger) '([^']+)'")
_RUNTIME_CONTEXT_RE = re.compile(r"Missing required runtime context fields: (.+?)\.$")


def _node_ids_from_text(text: str) -> list[str]:
    return list(dict.fromkeys(match.group(1) for match in _NODE_ID_RE.finditer(text)))


def make_issue(
    code: str,
    *,
    severity: str,
    message: str,
    next_action: str,
    source: str,
    **extra: Any,
) -> dict[str, Any]:
    issue = {
        "code": code,
        "severity": severity,
        "message": message,
        "next_action": next_action,
        "source": source,
    }
    for key, value in extra.items():
        if value not in (None, "", [], {}):
            issue[key] = value
    return issue


def validation_issue(message: str, *, severity: str = "error") -> dict[str, Any]:
    text = str(message or "")
    lower = text.lower()
    node_ids = _node_ids_from_text(text)
    code = "pipeline_validation_error"
    next_action = "Open the pipeline graph, correct the invalid node or edge, then save and rerun readiness."

    if "policy guard:" in lower:
        code = "approval_required"
        next_action = (
            "Route this mutating node through an approved human approval path, or make the agent/node read-only."
        )
    elif "no downstream executable nodes" in lower:
        code = "trigger_without_downstream"
        next_action = "Connect this trigger to at least one executable node, or disable/remove the trigger."
    elif "incoming edges. use an explicit merge node" in lower:
        code = "missing_merge_node"
        next_action = "Insert a logic/merge node before this target and route each branch into that merge."
    elif "references inaccessible mcp server" in lower:
        code = "inaccessible_mcp_server"
        next_action = "Select an MCP server owned by this user and run its connection test."
    elif "references inaccessible server" in lower:
        code = "inaccessible_server"
        next_action = "Select a server owned by this user, or grant access before running the pipeline."
    elif "unknown type" in lower:
        code = "unknown_node_type"
        next_action = "Replace this node with a node type from the current manifest."
    elif "graph_version" in lower:
        code = "unsupported_graph_version"
        next_action = "Open and resave the pipeline so it is migrated to the current graph version."
    elif "sourcehandle" in lower:
        code = "invalid_edge_handle"
        next_action = "Reconnect the edge using one of the handles allowed by the source node."
    elif "unreachable from every trigger" in lower:
        code = "unreachable_nodes"
        next_action = "Connect the listed nodes to an active trigger branch or remove them from the graph."
    elif "cycle or unreachable loop" in lower:
        code = "graph_cycle"
        next_action = "Break the cycle so execution can move forward through a finite path."
    elif "must include at least one trigger node" in lower:
        code = "missing_trigger"
        next_action = "Add a manual, schedule, webhook, or monitoring trigger node."
    elif "invalid cron expression" in lower:
        code = "invalid_schedule"
        next_action = "Replace the schedule with a valid cron expression."
    elif "missing required runtime context fields" in lower:
        code = "runtime_context_required"
        next_action = "Map these fields from trigger payload data or pass them when starting the run."
    elif "entry_node_id is required" in lower:
        code = "entry_trigger_required"
        next_action = "Select the trigger node that should start this run."
    elif "entry trigger" in lower and ("not found" in lower or "inactive" in lower):
        code = "entry_trigger_missing"
        next_action = "Select an active trigger node that exists in this pipeline."
    elif "no active manual trigger" in lower or "manual trigger" in lower and "not found" in lower:
        code = "manual_trigger_missing"
        next_action = "Add or enable a manual trigger, or choose one of the available manual trigger nodes."
    elif "multiple manual triggers" in lower:
        code = "manual_trigger_ambiguous"
        next_action = "Pass entry_node_id so the backend knows which manual trigger should start the run."
    elif "field" in lower and ("required" in lower or "must be" in lower):
        code = "node_field_invalid"
        next_action = "Fill or correct the field named in the validation message."

    fields: list[str] = []
    context_match = _RUNTIME_CONTEXT_RE.search(text)
    if context_match:
        fields = [field.strip() for field in context_match.group(1).split(",") if field.strip()]

    return make_issue(
        code,
        severity=severity,
        message=text,
        next_action=next_action,
        source="validation",
        node_ids=node_ids,
        fields=fields,
    )


def validation_issues(messages: list[str], *, severity: str = "error") -> list[dict[str, Any]]:
    return [validation_issue(message, severity=severity) for message in messages]


def integration_issue(requirement: dict[str, Any]) -> dict[str, Any] | None:
    severity = str(requirement.get("severity") or "")
    if severity not in {"error", "warning"}:
        return None
    kind = str(requirement.get("kind") or "")
    name = str(requirement.get("name") or "")
    status = str(requirement.get("status") or "")
    message = str(requirement.get("message") or name)
    code = "integration_requirement_not_ready"
    next_action = "Configure this integration for the listed node before running the pipeline."

    if kind == "llm":
        code = "llm_credentials_missing"
        next_action = "Set the provider API key/base URL, or switch the node to a configured provider."
    elif kind == "telegram" and "bot token" in name.lower():
        code = "telegram_token_missing"
        next_action = "Set TELEGRAM_BOT_TOKEN or bot_token on the Telegram node."
    elif kind == "telegram" and "chat" in name.lower():
        code = "telegram_chat_missing"
        next_action = "Set TELEGRAM_CHAT_ID/chat_id, or pass chat_id/tg_chat_id in runtime context."
    elif kind == "email" and "recipient" in name.lower():
        code = "email_recipient_missing"
        next_action = "Set PIPELINE_NOTIFY_EMAIL or to_email on the email node."
    elif kind == "email" and "smtp" in name.lower():
        code = "smtp_host_missing"
        next_action = "Set EMAIL_HOST or smtp_host for real SMTP delivery."
    elif kind == "mcp" and status == "missing":
        code = "mcp_server_missing"
        next_action = "Select an owner-accessible MCP server for the node and save the pipeline."
    elif kind == "mcp" and status == "failed":
        code = "mcp_server_failed"
        next_action = "Fix the MCP server connection and rerun the server test."
    elif kind == "mcp" and status == "untested":
        code = "mcp_server_untested"
        next_action = "Run the MCP server connection test before marking this pipeline production-ready."

    return make_issue(
        code,
        severity=severity,
        message=message,
        next_action=next_action,
        source="integration",
        node_ids=requirement.get("required_by_node_ids"),
        requirement=name,
        status=status,
    )


def runtime_context_issue(trigger: dict[str, Any]) -> dict[str, Any] | None:
    fields = list(trigger.get("unresolved_context_fields") or [])
    if not fields:
        return None
    label = trigger.get("name") or trigger.get("node_id") or trigger.get("id")
    return make_issue(
        "runtime_context_required",
        severity="warning",
        message=f"Trigger '{label}' needs runtime context fields: {', '.join(fields)}.",
        next_action="Map these fields from trigger payload data or pass them when starting the run.",
        source="runtime_context",
        trigger_ids=[trigger.get("id")],
        node_ids=[trigger.get("node_id")],
        fields=fields,
    )


def pipeline_scope_issue(missing_pipeline_ids: list[int], *, active_only: bool = False) -> dict[str, Any] | None:
    if not missing_pipeline_ids:
        return None
    scope_hint = " in the active-pipeline scope" if active_only else ""
    ids = ", ".join(str(item) for item in missing_pipeline_ids)
    return make_issue(
        "pipeline_not_found",
        severity="error",
        message=f"Pipeline id(s) not found or not accessible{scope_hint}: {ids}.",
        next_action="Check the pipeline id, owner/shared access, and whether active_only excluded it.",
        source="scope",
        pipeline_ids=missing_pipeline_ids,
    )


def runtime_limit_issue(limit_error: dict[str, Any]) -> dict[str, Any]:
    code = str(limit_error.get("code") or "runtime_limit_reached")
    limit = limit_error.get("limit")
    active = limit_error.get("active")
    scope = str(limit_error.get("scope") or "")
    return make_issue(
        code,
        severity="error",
        message=str(limit_error.get("error") or "Runtime limit reached."),
        next_action="Wait for active runs to finish, stop stale runs, or raise the configured run limit.",
        source="runtime_limit",
        limit=limit,
        active=active,
        scope=scope,
    )


def worker_issue(worker: dict[str, Any]) -> dict[str, Any] | None:
    if worker.get("ready"):
        return None
    name = str(worker.get("worker") or "")
    command = str(worker.get("command") or "")
    state = worker.get("state") if isinstance(worker.get("state"), dict) else {}
    status = str(state.get("status") or "")
    if status == "error":
        code = "worker_error"
    elif status == "running" and state.get("is_stale"):
        code = "worker_stale"
    else:
        code = "worker_not_running"
    return make_issue(
        code,
        severity="error",
        message=f"Worker '{name}' is not ready.",
        next_action=f"Start or restart the worker with: {command}" if command else "Start the required worker.",
        source="worker",
        worker=name,
        worker_kind=worker.get("worker_kind"),
    )
