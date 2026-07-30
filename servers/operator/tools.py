"""Operator-chat read tools over inventory, insights, forecasts, alerts.

F-08a: the tool implementations live in cohesive submodules
(``tools_hints`` / ``tools_inventory`` / ``tools_monitoring`` /
``tools_actions`` / ``tools_common``). This module keeps the public API stable via re-exports and
registers the operator ``AssistantAction`` specs.
"""

from __future__ import annotations

import contextlib

from app.assistant_actions import AssistantActionSpec, register_action
from servers.operator.tools_actions import (
    metric_series,
    promote_chat_memory,
    propose_plan,
    save_memory_lesson,
    server_memory,
    server_metrics,
)
from servers.operator.tools_hints import (
    extract_server_hint,
    normalize_host_hint,
    prefer_resolve_server_for_message,
    prepare_list_servers_arguments,
    server_matches_query,
    user_wants_inventory_card,
    user_wants_named_host_action,
)
from servers.operator.tools_inventory import (
    fleet_status,
    list_servers,
    resolve_server,
    server_info,
)
from servers.operator.tools_monitoring import (
    fleet_ai_insights,
    get_alert_detail,
    list_alerts,
    list_certificates,
    server_forecasts,
)

__all__ = [
    "extract_server_hint",
    "fleet_ai_insights",
    "fleet_status",
    "get_alert_detail",
    "list_alerts",
    "list_certificates",
    "list_servers",
    "metric_series",
    "normalize_host_hint",
    "prefer_resolve_server_for_message",
    "prepare_list_servers_arguments",
    "promote_chat_memory",
    "propose_plan",
    "register_operator_tools",
    "resolve_server",
    "save_memory_lesson",
    "server_forecasts",
    "server_info",
    "server_matches_query",
    "server_memory",
    "server_metrics",
    "user_wants_inventory_card",
    "user_wants_named_host_action",
]


def register_operator_tools() -> None:
    specs = [
        AssistantActionSpec(
            action_type="operator.resolve_server",
            label="Resolve server",
            description=(
                "Resolve one inventory host by name/host/id (e.g. lunix). "
                "Use for connect / SSH / diagnostics on a named host. "
                "Does NOT show the fleet inventory card in chat."
            ),
            required_feature="servers",
            risk="read",
            input_schema={
                "type": "object",
                "properties": {
                    "q": {
                        "type": "string",
                        "description": "Server name, host, or id (e.g. lunix)",
                    },
                    "name": {"type": "string", "description": "Alias for q"},
                },
            },
            handler=resolve_server,
        ),
        AssistantActionSpec(
            action_type="operator.list_servers",
            label="List servers",
            description=(
                "Inventory. For a named host ALWAYS use operator.resolve_server instead. "
                "Full list card appears only when the user asked to list servers "
                "(platform sets show_in_chat). Do not use this to «find» grafana/lunix."
            ),
            required_feature="servers",
            risk="read",
            input_schema={
                "type": "object",
                "properties": {
                    "q": {
                        "type": "string",
                        "description": "Filter by name/host/tag/id (e.g. grafana) — no fleet card",
                    },
                    "name": {"type": "string", "description": "Alias for q"},
                    "show_in_chat": {
                        "type": "boolean",
                        "description": "Platform-controlled; true only for explicit list-inventory requests.",
                    },
                },
            },
            handler=list_servers,
        ),
        AssistantActionSpec(
            action_type="operator.server_info",
            label="Server info",
            description="Get details for one accessible server (OS, host, ai_read_only). Accepts server_id or name.",
            required_feature="servers",
            risk="read",
            input_schema={
                "type": "object",
                "properties": {
                    "server_id": {"type": "integer"},
                    "name": {"type": "string", "description": "Server name if id unknown"},
                },
            },
            handler=server_info,
        ),
        AssistantActionSpec(
            action_type="operator.fleet_status",
            label="Fleet status",
            description="Fleet health summary: status counts and worst servers.",
            required_feature="servers",
            risk="read",
            handler=fleet_status,
        ),
        AssistantActionSpec(
            action_type="operator.server_metrics",
            label="Server metrics",
            description=(
                "Latest CPU/memory/disk for one server. disk_percent is ROOT (/) only; "
                "see disk_mounts for /mnt/* . Mirrored inventory may set mirrored_from_server_id."
            ),
            required_feature="servers",
            risk="read",
            input_schema={
                "type": "object",
                "properties": {"server_id": {"type": "integer"}},
                "required": ["server_id"],
            },
            handler=server_metrics,
        ),
        AssistantActionSpec(
            action_type="operator.server_forecasts",
            label="Server forecasts",
            description=(
                "Active capacity/cert forecasts. Pass server_id for one host. "
                "Fleet mode collapses duplicate predictions from mirrored host:port inventory."
            ),
            required_feature="servers",
            risk="read",
            input_schema={
                "type": "object",
                "properties": {"server_id": {"type": "integer", "description": "Optional server filter"}},
            },
            handler=server_forecasts,
        ),
        AssistantActionSpec(
            action_type="operator.list_alerts",
            label="List alerts",
            description=(
                "Monitoring alerts. For «разбери алерт #N» ALWAYS pass alert_id=N "
                "(returns focus package with mounts/prediction). Optional server_id. "
                "Fleet dumps collapse mirrored host:port clones."
            ),
            required_feature="servers",
            risk="read",
            input_schema={
                "type": "object",
                "properties": {
                    "alert_id": {"type": "integer", "description": "Investigate one alert by id"},
                    "server_id": {"type": "integer", "description": "Filter to one server"},
                    "unresolved_only": {"type": "boolean", "description": "Default true"},
                    "limit": {"type": "integer", "description": "Max rows (default 25)"},
                    "dedupe_hosts": {"type": "boolean", "description": "Collapse same host:port clones"},
                },
            },
            handler=list_alerts,
        ),
        AssistantActionSpec(
            action_type="operator.list_certificates",
            label="List certificates",
            description="TLS certificates with days left until expiry.",
            required_feature="servers",
            risk="read",
            handler=list_certificates,
        ),
        AssistantActionSpec(
            action_type="operator.fleet_ai_insights",
            label="Fleet AI insights",
            description="Latest AI analyst verdicts for fleet and servers.",
            required_feature="servers",
            risk="read",
            handler=fleet_ai_insights,
        ),
        AssistantActionSpec(
            action_type="operator.server_memory",
            label="Server memory",
            description="Operational memory card: incidents, habits, risks for one server.",
            required_feature="servers",
            risk="read",
            input_schema={
                "type": "object",
                "properties": {"server_id": {"type": "integer"}},
                "required": ["server_id"],
            },
            handler=server_memory,
        ),
        AssistantActionSpec(
            action_type="operator.memory.save_lesson",
            label="Save lesson to memory",
            description=(
                "Persist a short solved-problem lesson into server memory cards. "
                "Use after a successful diagnosis/fix. Requires title, lesson, server_ids."
            ),
            required_feature="servers",
            risk="internal_write",
            requires_confirmation=True,
            input_schema={
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "lesson": {"type": "string", "description": "What was wrong and how it was fixed"},
                    "server_ids": {"type": "array", "items": {"type": "integer"}},
                    "server_id": {"type": "integer"},
                    "run_dream": {"type": "boolean", "description": "Run nearline dream compaction after save"},
                    "chat_id": {"type": "integer"},
                },
                "required": ["title", "lesson"],
            },
            handler=save_memory_lesson,
        ),
        AssistantActionSpec(
            action_type="operator.memory.promote_chat",
            label="Promote chat to memory",
            description=(
                "When a conversation solved something important: distill it into durable "
                "server memory and optionally run a dream cycle. Prefer an explicit lesson summary."
            ),
            required_feature="servers",
            risk="internal_write",
            requires_confirmation=True,
            input_schema={
                "type": "object",
                "properties": {
                    "chat_id": {"type": "integer"},
                    "title": {"type": "string"},
                    "lesson": {"type": "string", "description": "Best: explicit root-cause + fix summary"},
                    "server_ids": {"type": "array", "items": {"type": "integer"}},
                    "run_dream": {"type": "boolean", "description": "Default true — compact into patterns"},
                },
            },
            handler=promote_chat_memory,
        ),
        AssistantActionSpec(
            action_type="operator.metric_series",
            label="Metric series",
            description="Time series for a metric (cpu_percent, memory_percent, disk_percent) for charts.",
            required_feature="servers",
            risk="read",
            input_schema={
                "type": "object",
                "properties": {
                    "server_id": {"type": "integer"},
                    "metric_key": {"type": "string", "description": "cpu_percent|memory_percent|disk_percent"},
                },
                "required": ["server_id"],
            },
            handler=metric_series,
        ),
        AssistantActionSpec(
            action_type="operator.propose_plan",
            label="Propose plan",
            description=(
                "Propose a multi-step plan checklist for complex tasks (>2 mutations). "
                "Operator approves once; then execute steps with tools."
            ),
            required_feature="orchestrator",
            risk="internal_write",
            requires_confirmation=True,
            input_schema={
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "steps": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "text": {"type": "string"},
                                "tool": {"type": "string"},
                                "input": {
                                    "type": "object",
                                    "description": (
                                        "Exact arguments that will be executed after approval. "
                                        "The platform rejects plan auto-run when they differ."
                                    ),
                                },
                            },
                            "required": ["text", "tool", "input"],
                        },
                    },
                },
                "required": ["title", "steps"],
            },
            handler=propose_plan,
        ),
    ]
    for spec in specs:
        # Duplicate registration is expected when Django calls ready() twice.
        with contextlib.suppress(ValueError):
            register_action(spec)
