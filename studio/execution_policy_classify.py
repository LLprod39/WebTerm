from __future__ import annotations

import re
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from app.command_execution_gate import evaluate_command_execution_gate
from studio.execution_policy_agents import classify_dynamic_agent_policy
from studio.execution_policy_types import (
    ExecutionPolicyDecision,
    PolicyActionClass,
    PolicyRiskLevel,
    _decision,
    _node_data,
)

MCP_MUTATING_TOOL_RE = re.compile(
    r"(^|[_\-.])(add|apply|assign|create|delete|disable|enable|grant|patch|remove|restart|revoke|set|start|stop|update|write)([_\-.]|$)",
    re.IGNORECASE,
)
SSH_MUTATING_COMMAND_RE = re.compile(
    r"\b(apt(-get)?\s+install|chmod|chown|docker\s+(restart|rm|run|stop)|kubectl\s+(apply|delete|patch|rollout)|rm\s+-|systemctl\s+(restart|reload|start|stop)|user(add|del|mod))\b",
    re.IGNORECASE,
)


def _redact_url(value: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    try:
        parsed = urlsplit(raw)
    except ValueError:
        return "[invalid-url]"
    if not parsed.scheme or not parsed.netloc:
        return raw[:400]
    query = urlencode([(key, "[redacted]") for key, _value in parse_qsl(parsed.query, keep_blank_values=True)])
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, query, "[redacted]" if parsed.fragment else ""))


def _classify_mcp_call(
    node: dict[str, Any],
    *,
    has_approved_approval_path: bool | None,
) -> list[ExecutionPolicyDecision]:
    data = _node_data(node)
    tool_name = str(data.get("tool_name") or "").strip()
    permission_mode = str(data.get("permission_mode") or "").strip().upper()
    risk_level = str(data.get("risk_level") or "").strip().lower()
    operation_kind = str(data.get("operation_kind") or "").strip()
    mutates_state = bool(data.get("mutates_state") or data.get("requires_approval"))
    looks_mutating = bool(tool_name and MCP_MUTATING_TOOL_RE.search(tool_name))
    mutates_state = mutates_state or looks_mutating
    mutates_state = mutates_state or permission_mode in {"ASSISTED", "AUTO_GUARDED", "AUTONOMOUS", "BREAK_GLASS"}
    if not mutates_state:
        return []

    action_class: PolicyActionClass = (
        "dangerous"
        if risk_level in {"dangerous", "critical", "break_glass"} or permission_mode == "BREAK_GLASS"
        else "mutating"
    )
    level: PolicyRiskLevel = "dangerous" if action_class == "dangerous" else "review"
    reasons = ["MCP tool may change state; review target, preflight, and verification before apply."]
    if data.get("requires_approval"):
        reasons.append("Tool metadata requires human approval.")
    if operation_kind:
        reasons.append(f"Operation kind: {operation_kind[:160]}.")
    if has_approved_approval_path is False:
        reasons.append("Missing approved human approval path.")

    return [
        _decision(
            node,
            stage="mcp_call",
            action_class=action_class,
            level=level,
            requires_approval=True,
            has_approved_approval_path=has_approved_approval_path,
            command=tool_name,
            categories=("mcp_mutation",),
            matched_patterns=(MCP_MUTATING_TOOL_RE.pattern,) if looks_mutating else (),
            reasons=tuple(reasons),
        )
    ]


def _classify_dynamic_agent(
    node: dict[str, Any],
    *,
    has_approved_approval_path: bool | None,
) -> list[ExecutionPolicyDecision]:
    policy = classify_dynamic_agent_policy(_node_data(node))
    if policy is None:
        return []
    reasons = list(policy.reasons)
    if has_approved_approval_path is False:
        reasons.append("Missing approved human approval path.")

    return [
        _decision(
            node,
            stage="agent_runtime",
            action_class="mutating",
            level="review",
            requires_approval=True,
            has_approved_approval_path=has_approved_approval_path,
            command=policy.command,
            categories=("dynamic_agent",),
            matched_patterns=policy.risky_tools,
            reasons=tuple(reasons),
        )
    ]


def _classify_external_output(
    node: dict[str, Any],
    *,
    has_approved_approval_path: bool | None,
) -> list[ExecutionPolicyDecision]:
    node_type = str(node.get("type") or "")
    data = _node_data(node)
    requires_approval = bool(data.get("requires_approval"))
    if node_type == "output/webhook":
        url = str(data.get("url") or "").strip()
        if not url:
            return []
        return [
            _decision(
                node,
                stage="webhook",
                action_class="external",
                level="review",
                requires_approval=requires_approval,
                has_approved_approval_path=has_approved_approval_path,
                command=_redact_url(url),
                categories=("external_side_effect", "webhook"),
                reasons=(
                    "Webhook sends workflow data to an external URL; review payload redaction and delivery target.",
                ),
            )
        ]
    if node_type == "output/email":
        recipients = str(data.get("to_email") or data.get("recipients") or "").strip()
        if not recipients:
            return []
        recipient_count = len([item for item in re.split(r"[,;\s]+", recipients) if item.strip()])
        return [
            _decision(
                node,
                stage="email",
                action_class="external",
                level="review",
                requires_approval=requires_approval,
                has_approved_approval_path=has_approved_approval_path,
                command=f"email:{recipient_count or 1} recipient(s)",
                categories=("external_side_effect", "email"),
                reasons=("Email output sends workflow data outside the run; review recipients and message content.",),
            )
        ]
    if node_type == "output/telegram":
        chat_id = str(data.get("chat_id") or data.get("tg_chat_id") or "").strip()
        bot_token = str(
            data.get("bot_token")
            or data.get("tg_bot_token")
            or data.get("telegram_bot_token")
            or data.get("bot_token_configured")
            or data.get("tg_bot_token_configured")
            or data.get("telegram_bot_token_configured")
            or ""
        ).strip()
        if not chat_id and not bot_token:
            return []
        return [
            _decision(
                node,
                stage="telegram",
                action_class="external",
                level="review",
                requires_approval=requires_approval,
                has_approved_approval_path=has_approved_approval_path,
                command=f"telegram_chat:{chat_id or '[configured]'}",
                categories=("external_side_effect", "telegram"),
                reasons=(
                    "Telegram output sends workflow data outside the run; review chat target and message content.",
                ),
            )
        ]
    return []


def _classify_ssh_cmd(
    node: dict[str, Any],
    *,
    has_approved_approval_path: bool | None,
) -> list[ExecutionPolicyDecision]:
    data = _node_data(node)
    commands: list[tuple[str, Any]] = [("command", data.get("command"))]
    commands.extend(("preflight", value) for value in (data.get("preflight_commands") or []))
    commands.extend(("verification", value) for value in (data.get("verification_commands") or []))

    decisions: list[ExecutionPolicyDecision] = []
    for stage, raw_command in commands:
        command = str(raw_command or "").strip()
        if not command:
            continue
        gate = evaluate_command_execution_gate(command)
        verdict = gate.risk
        looks_mutating = bool(SSH_MUTATING_COMMAND_RE.search(command))
        if not gate.requires_approval and not looks_mutating:
            continue
        reasons = list(verdict.reasons)
        if not reasons:
            reasons.append(
                "SSH command is outside the built-in read-only allowlist or cannot be classified safely."
            )
        if has_approved_approval_path is False:
            reasons.append("Missing approved human approval path.")
        decisions.append(
            _decision(
                node,
                stage=stage,
                action_class="dangerous" if verdict.is_dangerous else "mutating",
                level="dangerous" if verdict.is_dangerous else "review",
                requires_approval=True,
                has_approved_approval_path=has_approved_approval_path,
                command=command,
                categories=tuple(verdict.categories)
                if verdict.is_dangerous
                else (("unclassifiable_shell",) if gate.reason == "unclassifiable" else ("ssh_mutation",)),
                matched_patterns=tuple(verdict.matched_patterns)
                if verdict.is_dangerous
                else (SSH_MUTATING_COMMAND_RE.pattern,),
                reasons=tuple(reasons),
            )
        )
    return decisions


def _classify_ops_action(
    node: dict[str, Any],
    *,
    has_approved_approval_path: bool | None,
) -> list[ExecutionPolicyDecision]:
    node_type = str(node.get("type") or "")
    data = _node_data(node)
    action = str(data.get("action") or "").strip().lower()
    if node_type == "ops/file_action" and action != "write":
        return []
    if node_type == "ops/package_action" and action == "list_updates":
        return []
    if node_type == "ops/disk_cleanup" and action == "inspect":
        return []
    action_class: PolicyActionClass = (
        "dangerous" if node_type == "ops/process_action" and action == "kill_force" else "mutating"
    )
    reasons = ["OPS action mutates service/container/process/file/package/disk/alert state."]
    if has_approved_approval_path is False:
        reasons.append("Missing approved human approval path.")
    return [
        _decision(
            node,
            stage=node_type.removeprefix("ops/") or "ops_action",
            action_class=action_class,
            level="dangerous" if action_class == "dangerous" else "review",
            requires_approval=True,
            has_approved_approval_path=has_approved_approval_path,
            command=f"{action} {str(data.get('path') or data.get('packages') or data.get('service') or data.get('container') or data.get('pid') or '').strip()}".strip(),
            categories=("ops_mutation",),
            reasons=tuple(reasons),
        )
    ]
