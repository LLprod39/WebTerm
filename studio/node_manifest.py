from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any


def _empty_object_schema() -> dict[str, Any]:
    return {"type": "object", "properties": {}, "additionalProperties": True}


def _schema(properties: dict[str, Any] | None = None, *, required: tuple[str, ...] = ()) -> dict[str, Any]:
    schema: dict[str, Any] = {
        "type": "object",
        "properties": properties or {},
        "additionalProperties": True,
    }
    if required:
        schema["required"] = list(required)
    return schema


def _str(*, description: str = "", enum: tuple[str, ...] = (), default: str | None = None) -> dict[str, Any]:
    schema: dict[str, Any] = {"type": "string"}
    if description:
        schema["description"] = description
    if enum:
        schema["enum"] = list(enum)
    if default is not None:
        schema["default"] = default
    return schema


def _int(
    *,
    description: str = "",
    minimum: int | None = None,
    maximum: int | None = None,
    default: int | None = None,
) -> dict[str, Any]:
    schema: dict[str, Any] = {"type": "integer"}
    if description:
        schema["description"] = description
    if minimum is not None:
        schema["minimum"] = minimum
    if maximum is not None:
        schema["maximum"] = maximum
    if default is not None:
        schema["default"] = default
    return schema


def _bool(*, description: str = "", default: bool | None = None) -> dict[str, Any]:
    schema: dict[str, Any] = {"type": "boolean"}
    if description:
        schema["description"] = description
    if default is not None:
        schema["default"] = default
    return schema


def _array(items: dict[str, Any], *, description: str = "", default: list[Any] | None = None) -> dict[str, Any]:
    schema: dict[str, Any] = {"type": "array", "items": items}
    if description:
        schema["description"] = description
    if default is not None:
        schema["default"] = default
    return schema


def _obj(*, description: str = "") -> dict[str, Any]:
    schema = _empty_object_schema()
    if description:
        schema["description"] = description
    return schema


ON_FAILURE_SCHEMA = _str(
    enum=("abort", "continue"),
    default="abort",
    description="Execution behavior when this node returns an error.",
)
PERMISSION_MODE_SCHEMA = _str(
    enum=("SAFE", "ASK", "AUTO"),
    default="SAFE",
    description="Policy mode for tool or command execution.",
)
SERVER_ID_FIELDS = {
    "server_id": _int(description="Explicit WebTerm server id owned by the pipeline owner."),
    "server_id_context_key": _str(default="server_id", description="Context key to resolve server_id from."),
}
COMMON_SUCCESS_OUTPUT = _schema({"output": _str(description="Human-readable node result.")})


@dataclass(frozen=True, slots=True)
class NodeManifest:
    node_type: str
    category: str
    purpose: str
    source_handles: tuple[str, ...]
    risk_level: str = "read_only"
    mutates_state: bool = False
    supports_dry_run: bool = False
    requires_approval_by_default: bool = False
    recommended_verification: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()
    input_schema: dict[str, Any] = field(default_factory=_empty_object_schema)
    output_schema: dict[str, Any] = field(default_factory=_empty_object_schema)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_assistant_catalog_item(self) -> dict[str, Any]:
        return {
            "category": self.category,
            "purpose": self.purpose,
            "source_handles": list(self.source_handles),
            "risk_level": self.risk_level,
            "mutates_state": self.mutates_state,
            "supports_dry_run": self.supports_dry_run,
            "requires_approval_by_default": self.requires_approval_by_default,
            "recommended_verification": list(self.recommended_verification),
            "tags": list(self.tags),
            "input_schema": deepcopy(self.input_schema),
            "output_schema": deepcopy(self.output_schema),
        }

    def to_api_payload(self) -> dict[str, Any]:
        item = self.to_assistant_catalog_item()
        item["type"] = self.node_type
        item["metadata"] = deepcopy(self.metadata)
        return item


def _manifest(
    node_type: str,
    category: str,
    purpose: str,
    source_handles: tuple[str, ...],
    **kwargs: Any,
) -> NodeManifest:
    return NodeManifest(
        node_type=node_type,
        category=category,
        purpose=purpose,
        source_handles=source_handles,
        **kwargs,
    )


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
                "permission_mode": PERMISSION_MODE_SCHEMA, "max_iterations": _int(minimum=1, maximum=20, default=6),
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
                "skill_slugs": _array(_str(), description="Skills to apply during execution."), "permission_mode": PERMISSION_MODE_SCHEMA,
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
                "preflight_commands": _array(_str(), description="Read-only checks to run before command execution."),
                "verification_commands": _array(_str(), description="Checks to run after command execution."),
                "permission_mode": PERMISSION_MODE_SCHEMA,
                "on_failure": ON_FAILURE_SCHEMA,
            },
            required=("command",),
        ),
        output_schema=_schema({"output": _str(), "command": _obj(), "preflight": _array(_obj()), "verification": _array(_obj())}),
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
    "ops/server_snapshot": _manifest(
        "ops/server_snapshot",
        "Ops",
        "Structured read-only Linux server snapshot from existing WebTerm Linux UI collectors.",
        ("success", "error", "out"),
        risk_level="read_only",
        tags=("linux", "diagnostics", "snapshot"),
        input_schema=_schema(
            {
                **SERVER_ID_FIELDS,
                "sections": _array(
                    _str(enum=("overview", "services", "processes", "docker", "logs", "disk", "network", "packages")),
                    default=["overview", "services", "docker", "disk"],
                ),
                "log_source": _str(default="journal"),
                "service": _str(description="Optional service name for log sections."),
                "lines": _int(minimum=20, maximum=240, default=80),
                "limit": _int(minimum=1, maximum=500, default=80),
                "on_failure": ON_FAILURE_SCHEMA,
            }
        ),
        output_schema=_schema({"output": _str(), "snapshot": _obj()}),
    ),
    "ops/log_query": _manifest(
        "ops/log_query",
        "Ops",
        "Read-only Linux/service/Docker log collection with optional text filtering.",
        ("success", "error", "out"),
        risk_level="read_only",
        tags=("linux", "logs", "diagnostics", "incident"),
        input_schema=_schema(
            {
                **SERVER_ID_FIELDS,
                "source": _str(
                    enum=(
                        "journal",
                        "service",
                        "docker",
                        "syslog",
                        "messages",
                        "auth",
                        "nginx_error",
                        "nginx_access",
                        "apache_error",
                        "apache_access",
                    ),
                    default="journal",
                ),
                "service": _str(description="Required when source=service."),
                "container": _str(description="Required when source=docker."),
                "lines": _int(minimum=20, maximum=240, default=120),
                "filter_text": _str(description="Optional case-insensitive substring filter."),
                "on_failure": ON_FAILURE_SCHEMA,
            }
        ),
        output_schema=_schema({"output": _str(), "logs": _obj()}),
    ),
    "ops/file_action": _manifest(
        "ops/file_action",
        "Ops",
        "Read or write UTF-8 text files over the existing SFTP layer.",
        ("success", "error", "out"),
        risk_level="dynamic",
        mutates_state=True,
        supports_dry_run=True,
        requires_approval_by_default=True,
        recommended_verification=("ops/file_action", "output/report"),
        tags=("linux", "file", "config"),
        input_schema=_schema(
            {
                **SERVER_ID_FIELDS,
                "action": _str(enum=("read", "write"), default="read"),
                "path": _str(description="Remote text file path."),
                "content": _str(description="UTF-8 content for write action. Supports templates."),
                "allow_empty_content": _bool(default=False),
                "max_bytes": _int(minimum=1024, maximum=1048576, default=131072),
                "on_failure": ON_FAILURE_SCHEMA,
            },
            required=("path", "action"),
        ),
        output_schema=_schema({"output": _str(), "file": _obj()}),
    ),
    "ops/package_action": _manifest(
        "ops/package_action",
        "Ops",
        "List package updates or run explicit package install/update/remove actions.",
        ("success", "error", "out"),
        risk_level="dynamic",
        mutates_state=True,
        supports_dry_run=True,
        requires_approval_by_default=True,
        recommended_verification=("ops/package_action", "ops/server_snapshot", "output/report"),
        tags=("linux", "packages", "maintenance"),
        input_schema=_schema(
            {
                **SERVER_ID_FIELDS,
                "action": _str(enum=("list_updates", "install", "update", "remove"), default="list_updates"),
                "packages": _array(_str(), description="Explicit package names for install/update/remove."),
                "verify": _bool(default=True),
                "on_failure": ON_FAILURE_SCHEMA,
            },
            required=("action",),
        ),
        output_schema=_schema({"output": _str(), "packages": _obj(), "package_action": _obj()}),
    ),
    "ops/disk_cleanup": _manifest(
        "ops/disk_cleanup",
        "Ops",
        "Inspect disk usage or run bounded journal/tmp cleanup actions.",
        ("success", "error", "out"),
        risk_level="dynamic",
        mutates_state=True,
        supports_dry_run=True,
        requires_approval_by_default=True,
        recommended_verification=("ops/disk_cleanup", "ops/server_snapshot", "output/report"),
        tags=("linux", "disk", "cleanup", "maintenance"),
        input_schema=_schema(
            {
                **SERVER_ID_FIELDS,
                "action": _str(enum=("inspect", "journal_vacuum", "tmp_cleanup"), default="inspect"),
                "dry_run": _bool(default=False),
                "verify": _bool(default=True),
                "min_age_days": _int(minimum=1, maximum=365, default=7),
                "max_entries": _int(minimum=1, maximum=500, default=50),
                "vacuum_time_days": _int(minimum=1, maximum=365, default=14),
                "vacuum_size_mb": _int(minimum=64, maximum=102400),
                "on_failure": ON_FAILURE_SCHEMA,
            },
            required=("action",),
        ),
        output_schema=_schema({"output": _str(), "disk": _obj(), "disk_cleanup": _obj()}),
    ),
    "ops/backup_restore_check": _manifest(
        "ops/backup_restore_check",
        "Ops",
        "Read-only backup freshness and latest archive integrity check.",
        ("success", "error", "out"),
        risk_level="read_only",
        supports_dry_run=True,
        recommended_verification=("ops/backup_restore_check", "output/report"),
        tags=("linux", "backup", "restore", "verification"),
        input_schema=_schema(
            {
                **SERVER_ID_FIELDS,
                "action": _str(enum=("inspect", "verify_latest"), default="inspect"),
                "path": _str(description="Remote backup directory path."),
                "max_depth": _int(minimum=1, maximum=5, default=2),
                "max_files": _int(minimum=1, maximum=100, default=20),
                "max_age_hours": _int(minimum=1, maximum=8760, default=24),
                "on_failure": ON_FAILURE_SCHEMA,
            },
            required=("action", "path"),
        ),
        output_schema=_schema({"output": _str(), "backup_restore_check": _obj()}),
    ),
    "ops/service_action": _manifest(
        "ops/service_action",
        "Ops",
        "Structured systemd service action with preflight and verification.",
        ("success", "error", "out"),
        risk_level="mutating",
        mutates_state=True,
        supports_dry_run=True,
        requires_approval_by_default=True,
        recommended_verification=("ops/server_snapshot", "ops/http_check"),
        tags=("linux", "systemd", "service"),
        input_schema=_schema(
            {
                **SERVER_ID_FIELDS,
                "service": _str(description="systemd service name. Falls back to service_name runtime context when empty."),
                "action": _str(enum=("start", "stop", "restart", "reload"), default="restart"),
                "verify": _bool(default=True),
                "on_failure": ON_FAILURE_SCHEMA,
            },
            required=("service", "action"),
        ),
        output_schema=_schema({"output": _str(), "action_result": _obj()}),
    ),
    "ops/docker_action": _manifest(
        "ops/docker_action",
        "Ops",
        "Structured Docker container start/stop/restart with inspect/log verification.",
        ("success", "error", "out"),
        risk_level="mutating",
        mutates_state=True,
        supports_dry_run=True,
        requires_approval_by_default=True,
        recommended_verification=("ops/server_snapshot", "ops/http_check"),
        tags=("docker", "container"),
        input_schema=_schema(
            {
                **SERVER_ID_FIELDS,
                "container": _str(description="Docker container name or id."),
                "action": _str(enum=("start", "stop", "restart"), default="restart"),
                "include_logs": _bool(default=True),
                "verify": _bool(default=True),
                "lines": _int(minimum=20, maximum=240, default=80),
                "on_failure": ON_FAILURE_SCHEMA,
            },
            required=("container", "action"),
        ),
        output_schema=_schema({"output": _str(), "action_result": _obj()}),
    ),
    "ops/process_action": _manifest(
        "ops/process_action",
        "Ops",
        "Structured process terminate/kill action on a target server.",
        ("success", "error", "out"),
        risk_level="dangerous",
        mutates_state=True,
        supports_dry_run=True,
        requires_approval_by_default=True,
        recommended_verification=("ops/server_snapshot",),
        tags=("linux", "process", "break-glass"),
        input_schema=_schema(
            {
                **SERVER_ID_FIELDS,
                "pid": _int(description="Explicit process id."),
                "pid_context_key": _str(default="pid", description="Context key to resolve PID from."),
                "action": _str(enum=("terminate", "kill_force"), default="terminate"),
                "on_failure": ON_FAILURE_SCHEMA,
            },
            required=("action",),
        ),
        output_schema=_schema({"output": _str(), "action_result": _obj()}),
    ),
    "ops/http_check": _manifest(
        "ops/http_check",
        "Ops",
        "HTTP availability/content check with retries and expected statuses.",
        ("success", "error", "out"),
        risk_level="read_only",
        tags=("http", "health", "verification"),
        input_schema=_schema(
            {
                "url": _str(description="URL template to check."),
                "method": _str(enum=("GET", "HEAD"), default="GET"),
                "expected_status": _array(_int(minimum=100, maximum=599), default=[200]),
                "timeout_seconds": _int(minimum=1, maximum=120, default=15),
                "retries": _int(minimum=1, maximum=5, default=1),
                "body_contains": _str(description="Optional response body substring."),
                "on_failure": ON_FAILURE_SCHEMA,
            },
            required=("url",),
        ),
        output_schema=_schema({"output": _str(), "http_check": _obj()}),
    ),
    "ops/alert_update": _manifest(
        "ops/alert_update",
        "Ops",
        "Update a WebTerm monitoring alert, currently resolve-by-id.",
        ("success", "error", "out"),
        risk_level="mutating",
        mutates_state=True,
        tags=("monitoring", "alert"),
        input_schema=_schema(
            {
                "alert_id": _int(description="Explicit monitoring alert id."),
                "alert_id_context_key": _str(default="alert_id", description="Context key to resolve alert_id from."),
                "action": _str(enum=("resolve",), default="resolve"),
                "note": _str(description="Operator note stored in output."),
                "on_failure": ON_FAILURE_SCHEMA,
            }
        ),
        output_schema=_schema({"output": _str(), "alert": _obj()}),
    ),
    "logic/condition": _manifest(
        "logic/condition",
        "Logic",
        "Branch by checking a prior node output.",
        ("true", "false"),
        tags=("branch",),
        input_schema=_schema(
            {
                "source_node_id": _str(description="Optional node output to inspect."),
                "check_type": _str(enum=("contains", "not_contains", "status_ok", "status_failed", "always_true"), default="contains"),
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
        output_schema=_schema({"decision": _str(enum=("received", "timeout")), "operator_response": _str(), "output": _str()}),
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


def get_node_manifest(node_type: str) -> NodeManifest | None:
    return NODE_MANIFESTS.get(str(node_type or "").strip())


def allowed_source_handles(node_type: str) -> frozenset[str]:
    manifest = get_node_manifest(node_type)
    if manifest is None:
        return frozenset({"out"})
    return frozenset(manifest.source_handles)


def assistant_node_catalog() -> dict[str, dict[str, Any]]:
    return {node_type: manifest.to_assistant_catalog_item() for node_type, manifest in NODE_MANIFESTS.items()}


def node_manifest_payload() -> list[dict[str, Any]]:
    return [manifest.to_api_payload() for manifest in NODE_MANIFESTS.values()]
