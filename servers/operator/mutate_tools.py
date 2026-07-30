"""Operator mutate tools: run_command, fanout, playbooks, runbooks, alerts.

F-08a: the tool implementations live in focused submodules
(``operator_mutate_exec`` / ``_playbooks`` / ``_schedule``). This module keeps
the public API stable via re-exports and registers the operator mutate specs.
"""

from __future__ import annotations

import contextlib

from app.assistant_actions import AssistantActionSpec, register_action
from servers.operator.mutate_exec import run_command, run_fanout
from servers.operator.mutate_playbooks import create_playbook, resolve_alert, run_playbook, save_runbook
from servers.operator.mutate_schedule import schedule_agent, undo_last_action

__all__ = [
    "create_playbook",
    "register_operator_mutate_tools",
    "resolve_alert",
    "run_command",
    "run_fanout",
    "run_playbook",
    "save_runbook",
    "schedule_agent",
    "undo_last_action",
]


def register_operator_mutate_tools() -> None:
    specs = [
        AssistantActionSpec(
            action_type="operator.run_command",
            label="Run command",
            description="Execute a shell command on one accessible SSH server (confirm required).",
            required_feature="servers",
            risk="mutating",
            requires_confirmation=True,
            input_schema={
                "type": "object",
                "properties": {
                    "server_id": {"type": "integer"},
                    "command": {"type": "string"},
                    "allow_destructive": {"type": "boolean"},
                },
                "required": ["server_id", "command"],
            },
            handler=run_command,
        ),
        AssistantActionSpec(
            action_type="operator.run_fanout",
            label="Fan-out command",
            description="Run the same command on many servers; returns a result matrix.",
            required_feature="servers",
            risk="mutating",
            requires_confirmation=True,
            input_schema={
                "type": "object",
                "properties": {
                    "server_ids": {"type": "array", "items": {"type": "integer"}},
                    "tag": {"type": "string"},
                    "command": {"type": "string"},
                    "concurrency": {"type": "integer"},
                    "allow_destructive": {"type": "boolean"},
                },
                "required": ["command"],
            },
            handler=run_fanout,
        ),
        AssistantActionSpec(
            action_type="operator.create_playbook",
            label="Create playbook",
            description=(
                "Create a playbook. For ansible pass yaml. For a command runbook pass "
                "steps as a list of {command, description}."
            ),
            required_feature="servers",
            risk="internal_write",
            requires_confirmation=True,
            input_schema={
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "yaml": {"type": "string"},
                    "steps": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "command": {"type": "string"},
                                "description": {"type": "string"},
                            },
                            "required": ["command"],
                        },
                    },
                    "tasks": {"type": "array"},
                    "description": {"type": "string"},
                },
            },
            handler=create_playbook,
        ),
        AssistantActionSpec(
            action_type="operator.run_playbook",
            label="Run playbook",
            description="Start a playbook run (async). Use check_mode for dry-run.",
            required_feature="servers",
            risk="mutating",
            requires_confirmation=True,
            input_schema={
                "type": "object",
                "properties": {
                    "playbook_id": {"type": "integer"},
                    "server_ids": {"type": "array", "items": {"type": "integer"}},
                    "check_mode": {"type": "boolean"},
                    "concurrency": {"type": "integer"},
                },
                "required": ["playbook_id", "server_ids"],
            },
            handler=run_playbook,
        ),
        AssistantActionSpec(
            action_type="operator.save_runbook",
            label="Save runbook",
            description="Save a successful command chain as a reusable runbook playbook.",
            required_feature="servers",
            risk="internal_write",
            requires_confirmation=True,
            input_schema={
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "steps": {"type": "array"},
                    "description": {"type": "string"},
                },
                "required": ["title", "steps"],
            },
            handler=save_runbook,
        ),
        AssistantActionSpec(
            action_type="operator.resolve_alert",
            label="Resolve alert",
            description="Mark a monitoring alert as resolved.",
            required_feature="servers",
            risk="internal_write",
            requires_confirmation=True,
            input_schema={
                "type": "object",
                "properties": {"alert_id": {"type": "integer"}},
                "required": ["alert_id"],
            },
            handler=resolve_alert,
        ),
        AssistantActionSpec(
            action_type="operator.undo_last",
            label="Undo last action",
            description="Reverse the last undoable operator action when undo_payload is available.",
            required_feature="servers",
            risk="mutating",
            requires_confirmation=True,
            input_schema={
                "type": "object",
                "properties": {"action_id": {"type": "integer"}},
            },
            handler=undo_last_action,
        ),
        AssistantActionSpec(
            action_type="operator.schedule_agent",
            label="Schedule agent",
            description=(
                "Schedule an existing agent to run recurrently. Use daily_time 'HH:MM' "
                "for a daily run, weekdays [0-6] (Mon=0) for weekly, schedule_minutes for "
                "an interval, or cron. Optional deliver_to_chat posts the report here."
            ),
            required_feature="agents",
            risk="internal_write",
            requires_confirmation=True,
            input_schema={
                "type": "object",
                "properties": {
                    "agent_id": {"type": "integer"},
                    "schedule_minutes": {"type": "integer"},
                    "daily_hour": {"type": "integer"},
                    "daily_time": {"type": "string", "description": "HH:MM local time"},
                    "weekdays": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "description": "0=Mon … 6=Sun for weekly schedules",
                    },
                    "cron": {"type": "string"},
                    "deliver_to_chat": {"type": "boolean"},
                },
                "required": ["agent_id"],
            },
            handler=schedule_agent,
        ),
    ]
    for spec in specs:
        with contextlib.suppress(ValueError):
            register_action(spec)
