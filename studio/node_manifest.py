from __future__ import annotations

from typing import Any

from app.plugins.studio_nodes import plugin_studio_node_manifests

from .node_manifest_common import (
    COMMON_SUCCESS_OUTPUT,
    ON_FAILURE_SCHEMA,
    PERMISSION_MODE_SCHEMA,
    SERVER_ID_FIELDS,
    NodeManifest,
    _array,
    _bool,
    _int,
    _manifest,
    _obj,
    _schema,
    _str,
)
from .node_manifest_ops import OPS_NODE_MANIFESTS

NODE_MANIFESTS: dict[str, NodeManifest] = {
    "trigger/manual": _manifest(
        "trigger/manual",
        "Triggers",
        "Manual operator start. Use for test runs and human-launched workflows.",
        ("out",),
        tags=("entrypoint", "manual"),
        input_schema=_schema({"is_active": _bool(default=True)}),
        output_schema=_schema({"trigger": _obj(), "context": _obj()}),
    ),
    "trigger/webhook": _manifest(
        "trigger/webhook",
        "Triggers",
        "HTTP POST start. Use when an external system starts a pipeline.",
        ("out",),
        risk_level="integration",
        tags=("entrypoint", "http"),
        input_schema=_schema(
            {
                "is_active": _bool(default=True),
                "webhook_payload_map": _obj(description="Mapping from incoming webhook payload into pipeline context."),
            }
        ),
        output_schema=_schema({"trigger": _obj(), "payload": _obj(), "context": _obj()}),
    ),
    "trigger/schedule": _manifest(
        "trigger/schedule",
        "Triggers",
        "Cron-like scheduled start.",
        ("out",),
        tags=("entrypoint", "scheduled"),
        input_schema=_schema(
            {
                "is_active": _bool(default=True),
                "cron_expression": _str(description="Five-field cron expression."),
            }
        ),
        output_schema=_schema({"trigger": _obj(), "context": _obj()}),
    ),
    "trigger/monitoring": _manifest(
        "trigger/monitoring",
        "Triggers",
        "Start from server monitoring alerts.",
        ("out",),
        tags=("entrypoint", "monitoring", "incident"),
        input_schema=_schema(
            {
                "is_active": _bool(default=True),
                "monitoring_filters": _obj(description="Alert filters such as server_ids, severities and alert_types."),
            }
        ),
        output_schema=_schema({"trigger": _obj(), "alert": _obj(), "context": _obj()}),
    ),
    "agent/react": _manifest(
        "agent/react",
        "Agents",
        "Ops agent that reasons and uses server/tools according to policy.",
        ("success", "error", "out"),
        risk_level="dynamic",
        tags=("ai", "agent", "ops"),
        input_schema=_schema(
            {
                "goal": _str(description="Operational goal for the agent."),
                "agent_config_id": _int(description="Optional saved agent configuration id."),
                "server_ids": _array(_int(), description="Server ids available to the agent."),
                "mcp_server_ids": _array(_int(), description="MCP server ids available to the agent."),
                "skill_slugs": _array(_str(), description="Skills to apply during execution."),
                "permission_mode": PERMISSION_MODE_SCHEMA,
                "sudo_policy": _str(enum=("inherit", "disabled", "ask", "approved"), default="inherit"),
                "max_iterations": _int(minimum=1, maximum=20, default=6),
                "on_failure": ON_FAILURE_SCHEMA,
            }
        ),
        output_schema=COMMON_SUCCESS_OUTPUT,
    ),
    "agent/multi": _manifest(
        "agent/multi",
        "Agents",
        "Multi-server or multi-agent investigation step.",
        ("success", "error", "out"),
        risk_level="dynamic",
        tags=("ai", "agent", "multi"),
        input_schema=_schema(
            {
                "goal": _str(description="Investigation goal."),
                "server_ids": _array(_int(), description="Server ids to inspect."),
                "mcp_server_ids": _array(_int(), description="MCP server ids to use."),
                "skill_slugs": _array(_str(), description="Skills to apply during execution."),
                "permission_mode": PERMISSION_MODE_SCHEMA,
                "sudo_policy": _str(enum=("inherit", "disabled", "ask", "approved"), default="inherit"),
                "on_failure": ON_FAILURE_SCHEMA,
            }
        ),
        output_schema=COMMON_SUCCESS_OUTPUT,
    ),
    "agent/ssh_cmd": _manifest(
        "agent/ssh_cmd",
        "Agents",
        "Direct SSH command with preflight and verification commands.",
        ("success", "error", "out"),
        risk_level="dynamic",
        supports_dry_run=True,
        tags=("ssh", "command"),
        input_schema=_schema(
            {
                **SERVER_ID_FIELDS,
                "command": _str(description="Command template to execute over SSH."),
                "dry_run": _bool(default=False, description="Preview a changing command without executing it."),
                "preflight_commands": _array(_str(), description="Read-only checks to run before command execution."),
                "verification_commands": _array(_str(), description="Checks to run after command execution."),
                "permission_mode": PERMISSION_MODE_SCHEMA,
                "sudo_policy": _str(enum=("disabled", "ask", "approved"), default="disabled"),
                "on_failure": ON_FAILURE_SCHEMA,
            },
            required=("command",),
        ),
        output_schema=_schema(
            {
                "output": _str(),
                "command": _obj(),
                "preflight": _array(_obj()),
                "verification": _array(_obj()),
                "change_preview": _obj(),
            }
        ),
    ),
    "agent/llm_query": _manifest(
        "agent/llm_query",
        "Agents",
        "Direct LLM reasoning step over previous outputs/context.",
        ("success", "error", "out"),
        risk_level="read_only",
        tags=("ai", "analysis"),
        input_schema=_schema(
            {
                "provider": _str(enum=("gemini", "openai"), default="gemini"),
                "model": _str(description="Optional model override."),
                "system_prompt": _str(description="System instructions for the LLM."),
                "prompt": _str(description="Prompt template; can reference context variables."),
                "include_all_outputs": _bool(default=True),
                "on_failure": ON_FAILURE_SCHEMA,
            },
            required=("prompt",),
        ),
        output_schema=_schema({"output": _str(), "provider": _str(), "model": _str()}),
    ),
    "agent/mcp_call": _manifest(
        "agent/mcp_call",
        "Agents",
        "Pinned MCP tool call with JSON arguments.",
        ("success", "error", "out"),
        risk_level="dynamic",
        supports_dry_run=True,
        tags=("mcp", "tool"),
        input_schema=_schema(
            {
                "mcp_server_id": _int(description="MCP server id owned by the pipeline owner."),
                "tool_name": _str(description="MCP tool name to call."),
                "arguments": _obj(description="JSON arguments sent to the MCP tool."),
                "arguments_text": _str(description="Optional JSON text mirror used by the editor."),
                "permission_mode": PERMISSION_MODE_SCHEMA,
                "skill_slugs": _array(_str(), description="Skills whose policy pack should constrain the call."),
                "on_failure": ON_FAILURE_SCHEMA,
            },
            required=("mcp_server_id", "tool_name"),
        ),
        output_schema=_schema({"output": _str(), "tool_result": _obj(), "policy_messages": _array(_str())}),
    ),
    **OPS_NODE_MANIFESTS,
    "logic/condition": _manifest(
        "logic/condition",
        "Logic",
        "Branch by checking a prior node output.",
        ("true", "false"),
        tags=("branch",),
        input_schema=_schema(
            {
                "source_node_id": _str(description="Optional node output to inspect."),
                "check_type": _str(
                    enum=("contains", "not_contains", "status_ok", "status_failed", "always_true"), default="contains"
                ),
                "check_value": _str(description="Substring used by contains/not_contains checks."),
            }
        ),
        output_schema=_schema({"matched": _bool(), "checked_value": _str()}),
    ),
    "logic/parallel": _manifest(
        "logic/parallel",
        "Logic",
        "Fan out work into parallel branches.",
        ("out",),
        tags=("fanout",),
        input_schema=_schema({"branch_mode": _str(default="all")}),
        output_schema=_schema({"branches": _array(_str())}),
    ),
    "logic/merge": _manifest(
        "logic/merge",
        "Logic",
        "Join branches back together before continuing.",
        ("out",),
        tags=("join",),
        input_schema=_schema({"merge_strategy": _str(default="collect")}),
        output_schema=_schema({"merged": _obj()}),
    ),
    "logic/wait": _manifest(
        "logic/wait",
        "Logic",
        "Pause execution for a configured duration.",
        ("done", "out"),
        tags=("pause",),
        input_schema=_schema({"duration_minutes": _int(minimum=1, maximum=1440, default=5)}),
        output_schema=_schema({"output": _str(), "duration_minutes": _int()}),
    ),
    "logic/human_approval": _manifest(
        "logic/human_approval",
        "Logic",
        "Pause until an operator approves/rejects/times out.",
        ("approved", "rejected", "timeout"),
        risk_level="control",
        tags=("approval", "human-in-the-loop"),
        input_schema=_schema(
            {
                "message": _str(description="Approval request template."),
                "manual_link_only": _bool(default=False),
                "approver_username": _str(description="Distinct active platform user assigned to decide."),
                "timeout_minutes": _int(minimum=1, maximum=4320, default=60),
                "email_subject": _str(description="Optional email subject template."),
                "tg_chat_id": _str(description="Optional Telegram chat id override."),
                "telegram_message": _str(description="Optional Telegram message template."),
            }
        ),
        output_schema=_schema({"decision": _str(enum=("approved", "rejected", "timeout")), "output": _str()}),
    ),
    "logic/telegram_input": _manifest(
        "logic/telegram_input",
        "Logic",
        "Ask an operator for a plain-text Telegram reply. This is not a trigger.",
        ("received", "timeout"),
        risk_level="control",
        tags=("telegram", "human-in-the-loop"),
        input_schema=_schema(
            {
                "message": _str(description="Prompt template sent to Telegram."),
                "tg_chat_id": _str(description="Optional Telegram chat id override."),
                "timeout_minutes": _int(minimum=1, maximum=1440, default=30),
            }
        ),
        output_schema=_schema(
            {"decision": _str(enum=("received", "timeout")), "operator_response": _str(), "output": _str()}
        ),
    ),
    "output/report": _manifest(
        "output/report",
        "Output",
        "Generate a markdown report from prior node outputs.",
        ("success", "error", "out"),
        tags=("report",),
        input_schema=_schema(
            {
                "subject": _str(default="Pipeline Report: {pipeline_name}"),
                "template": _str(description="Markdown report template."),
            }
        ),
        output_schema=_schema({"output": _str(), "report": _str()}),
    ),
    "output/webhook": _manifest(
        "output/webhook",
        "Output",
        "Send results to an external webhook.",
        ("success", "error", "out"),
        risk_level="egress",
        tags=("http", "egress"),
        input_schema=_schema(
            {
                "url": _str(description="Webhook URL template."),
                "method": _str(enum=("POST", "PUT", "PATCH"), default="POST"),
                "headers": _obj(description="Extra HTTP headers."),
                "extra_payload": _obj(description="Extra JSON payload."),
                "timeout_seconds": _int(minimum=1, maximum=120, default=30),
            },
            required=("url",),
        ),
        output_schema=_schema({"output": _str(), "status_code": _int()}),
    ),
    "output/email": _manifest(
        "output/email",
        "Output",
        "Send an email notification/report.",
        ("success", "error", "out"),
        risk_level="egress",
        tags=("email", "egress"),
        input_schema=_schema(
            {
                "to_email": _str(description="Recipient email. Falls back to notification settings when empty."),
                "subject": _str(default="Pipeline Report: {pipeline_name}"),
                "body": _str(description="Email body template."),
            }
        ),
        output_schema=_schema({"output": _str(), "status": _str()}),
    ),
    "output/telegram": _manifest(
        "output/telegram",
        "Output",
        "Send a Telegram message. This does not wait for a reply.",
        ("success", "error", "out"),
        risk_level="egress",
        tags=("telegram", "egress"),
        input_schema=_schema(
            {
                "chat_id": _str(description="Telegram chat id. Falls back to notification settings when empty."),
                "message": _str(description="Telegram message template."),
            }
        ),
        output_schema=_schema({"output": _str(), "message_ids": _array(_int()), "last_message_id": _int()}),
    ),
}

KNOWN_NODE_TYPES = frozenset(NODE_MANIFESTS)
TRIGGER_NODE_TYPES = frozenset(
    node_type for node_type, manifest in NODE_MANIFESTS.items() if manifest.category == "Triggers"
)
OPS_NODE_TYPES = frozenset(node_type for node_type, manifest in NODE_MANIFESTS.items() if manifest.category == "Ops")


def _plugin_node_manifest_from_payload(payload: dict[str, Any]) -> NodeManifest:
    return NodeManifest(
        node_type=str(payload.get("type") or ""),
        category=str(payload.get("category") or "Plugin"),
        purpose=str(payload.get("purpose") or ""),
        source_handles=tuple(str(item) for item in payload.get("source_handles") or ("out",)),
        risk_level=str(payload.get("risk_level") or "read_only"),
        mutates_state=bool(payload.get("mutates_state")),
        supports_dry_run=bool(payload.get("supports_dry_run")),
        requires_approval_by_default=bool(payload.get("requires_approval_by_default")),
        recommended_verification=tuple(str(item) for item in payload.get("recommended_verification") or ()),
        tags=tuple(str(item) for item in payload.get("tags") or ()),
        input_schema=dict(payload.get("input_schema") or {}),
        output_schema=dict(payload.get("output_schema") or {}),
        metadata=dict(payload.get("metadata") or {}),
    )


def runtime_node_manifests(enabled_plugin_ids: set[str] | None = None) -> dict[str, NodeManifest]:
    manifests = dict(NODE_MANIFESTS)
    for payload in plugin_studio_node_manifests(enabled_plugin_ids):
        manifest = _plugin_node_manifest_from_payload(payload)
        if manifest.node_type:
            manifests[manifest.node_type] = manifest
    return manifests


def runtime_known_node_types(enabled_plugin_ids: set[str] | None = None) -> frozenset[str]:
    return frozenset(runtime_node_manifests(enabled_plugin_ids))


def get_node_manifest(node_type: str) -> NodeManifest | None:
    return runtime_node_manifests().get(str(node_type or "").strip())


def allowed_source_handles(node_type: str) -> frozenset[str]:
    manifest = get_node_manifest(node_type)
    if manifest is None:
        return frozenset({"out"})
    return frozenset(manifest.source_handles)


def assistant_node_catalog() -> dict[str, dict[str, Any]]:
    return {node_type: manifest.to_assistant_catalog_item() for node_type, manifest in NODE_MANIFESTS.items()}


def node_manifest_payload(enabled_plugin_ids: set[str] | None = None) -> list[dict[str, Any]]:
    return [manifest.to_api_payload() for manifest in runtime_node_manifests(enabled_plugin_ids).values()]
