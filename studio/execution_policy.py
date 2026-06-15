from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Literal
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from app.tools.safety import evaluate_command_safety

PolicyRiskLevel = Literal["review", "dangerous"]
PolicyActionClass = Literal["external", "mutating", "dangerous"]

MCP_MUTATING_TOOL_RE = re.compile(
    r"(^|[_\-.])(add|apply|assign|create|delete|disable|enable|grant|patch|remove|restart|revoke|set|start|stop|update|write)([_\-.]|$)",
    re.IGNORECASE,
)
SSH_MUTATING_COMMAND_RE = re.compile(
    r"\b(apt(-get)?\s+install|chmod|chown|docker\s+(restart|rm|run|stop)|kubectl\s+(apply|delete|patch|rollout)|rm\s+-|systemctl\s+(restart|reload|start|stop)|user(add|del|mod))\b",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class ExecutionPolicyDecision:
    node_id: str
    node_label: str
    node_type: str
    stage: str
    action_class: PolicyActionClass
    level: PolicyRiskLevel
    requires_approval: bool
    has_approved_approval_path: bool | None
    allowed: bool
    command: str = ""
    categories: tuple[str, ...] = field(default_factory=tuple)
    matched_patterns: tuple[str, ...] = field(default_factory=tuple)
    reasons: tuple[str, ...] = field(default_factory=tuple)

    def validation_error(self) -> str | None:
        if self.allowed or not self.requires_approval:
            return None
        return (
            f"Policy guard: {self.action_class} node '{self.node_id}' ({self.node_label}) "
            "requires an approved human approval path."
        )

    def to_risk_item(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "node_label": self.node_label,
            "stage": self.stage,
            "command": self.command[:400],
            "level": self.level,
            "categories": list(self.categories),
            "matched_patterns": list(self.matched_patterns),
            "reasons": list(self.reasons),
            "requires_approval": self.requires_approval,
            "has_approved_approval_path": self.has_approved_approval_path,
            "allowed": self.allowed,
            "action_class": self.action_class,
        }


def _node_data(node: dict[str, Any]) -> dict[str, Any]:
    data = node.get("data")
    return data if isinstance(data, dict) else {}


def _node_label(node: dict[str, Any]) -> str:
    data = _node_data(node)
    return str(data.get("label") or data.get("tool_name") or node.get("id") or node.get("type") or "node")


def _node_id(node: dict[str, Any]) -> str:
    return str(node.get("id") or "").strip()


def _normalized_handle(raw: Any) -> str:
    value = str(raw or "").strip()
    return value or "out"


def _incoming_map(edges: list[dict[str, Any]] | None) -> dict[str, list[dict[str, Any]]]:
    incoming: dict[str, list[dict[str, Any]]] = {}
    for edge in edges or []:
        if not isinstance(edge, dict):
            continue
        target = str(edge.get("target") or "").strip()
        if not target:
            continue
        incoming.setdefault(target, []).append(edge)
    return incoming


def _id_map(nodes: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {
        _node_id(node): node
        for node in nodes
        if isinstance(node, dict) and _node_id(node)
    }


def _all_paths_have_approved_approval(
    node_id: str,
    *,
    id_to_node: dict[str, dict[str, Any]],
    incoming_edges: dict[str, list[dict[str, Any]]],
    memo: dict[str, bool],
) -> bool:
    if node_id in memo:
        return memo[node_id]
    incoming = incoming_edges.get(node_id, [])
    if not incoming:
        memo[node_id] = False
        return False
    for edge in incoming:
        source = str(edge.get("source") or "").strip()
        source_node = id_to_node.get(source)
        if not source_node:
            memo[node_id] = False
            return False
        if str(source_node.get("type") or "") == "logic/human_approval" and _normalized_handle(edge.get("sourceHandle")) == "approved":
            continue
        if not _all_paths_have_approved_approval(
            source,
            id_to_node=id_to_node,
            incoming_edges=incoming_edges,
            memo=memo,
        ):
            memo[node_id] = False
            return False
    memo[node_id] = True
    return True


def _approval_state(
    node_id: str,
    *,
    id_to_node: dict[str, dict[str, Any]] | None,
    incoming_edges: dict[str, list[dict[str, Any]]] | None,
    memo: dict[str, bool],
) -> bool | None:
    if id_to_node is None or incoming_edges is None:
        return None
    return _all_paths_have_approved_approval(
        node_id,
        id_to_node=id_to_node,
        incoming_edges=incoming_edges,
        memo=memo,
    )


def _decision(
    node: dict[str, Any],
    *,
    stage: str,
    action_class: PolicyActionClass,
    level: PolicyRiskLevel,
    requires_approval: bool,
    has_approved_approval_path: bool | None,
    command: str = "",
    categories: tuple[str, ...] = (),
    matched_patterns: tuple[str, ...] = (),
    reasons: tuple[str, ...] = (),
) -> ExecutionPolicyDecision:
    allowed = not requires_approval or has_approved_approval_path is True
    return ExecutionPolicyDecision(
        node_id=_node_id(node),
        node_label=_node_label(node),
        node_type=str(node.get("type") or ""),
        stage=stage,
        action_class=action_class,
        level=level,
        requires_approval=requires_approval,
        has_approved_approval_path=has_approved_approval_path,
        allowed=allowed,
        command=command,
        categories=categories,
        matched_patterns=matched_patterns,
        reasons=reasons,
    )


def _is_nonblank(value: Any) -> bool:
    return bool(str(value or "").strip())


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
                reasons=("Webhook sends workflow data to an external URL; review payload redaction and delivery target.",),
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
        bot_token = str(data.get("bot_token") or data.get("tg_bot_token") or "").strip()
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
                reasons=("Telegram output sends workflow data outside the run; review chat target and message content.",),
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
        verdict = evaluate_command_safety(command)
        looks_mutating = bool(SSH_MUTATING_COMMAND_RE.search(command))
        if not verdict.is_dangerous and not looks_mutating:
            continue
        reasons = list(verdict.reasons) if verdict.is_dangerous else ["SSH command appears to mutate system state."]
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
                categories=tuple(verdict.categories) if verdict.is_dangerous else ("ssh_mutation",),
                matched_patterns=tuple(verdict.matched_patterns) if verdict.is_dangerous else (SSH_MUTATING_COMMAND_RE.pattern,),
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
    action_class: PolicyActionClass = "dangerous" if node_type == "ops/process_action" and action == "kill_force" else "mutating"
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


def build_execution_policy_decisions(
    *,
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]] | None = None,
    id_to_node: dict[str, dict[str, Any]] | None = None,
    incoming_edges: dict[str, list[dict[str, Any]]] | None = None,
) -> list[ExecutionPolicyDecision]:
    if not isinstance(nodes, list):
        return []
    if id_to_node is None and edges is not None:
        id_to_node = _id_map(nodes)
    if incoming_edges is None and edges is not None:
        incoming_edges = _incoming_map(edges)

    approval_memo: dict[str, bool] = {}
    decisions: list[ExecutionPolicyDecision] = []
    for node in nodes:
        if not isinstance(node, dict):
            continue
        node_type = str(node.get("type") or "")
        node_id = _node_id(node)
        has_approval = _approval_state(
            node_id,
            id_to_node=id_to_node,
            incoming_edges=incoming_edges,
            memo=approval_memo,
        )
        if node_type == "agent/mcp_call":
            decisions.extend(_classify_mcp_call(node, has_approved_approval_path=has_approval))
        elif node_type == "agent/ssh_cmd":
            decisions.extend(_classify_ssh_cmd(node, has_approved_approval_path=has_approval))
        elif node_type in {"ops/service_action", "ops/docker_action", "ops/process_action", "ops/file_action", "ops/package_action", "ops/disk_cleanup", "ops/alert_update"}:
            decisions.extend(_classify_ops_action(node, has_approved_approval_path=has_approval))
        elif node_type in {"output/webhook", "output/email", "output/telegram"}:
            decisions.extend(_classify_external_output(node, has_approved_approval_path=has_approval))
    return decisions


def summarize_execution_policy_decisions(decisions: list[ExecutionPolicyDecision]) -> dict[str, Any]:
    items = [decision.to_risk_item() for decision in decisions]
    return {
        "version": 1,
        "total": len(decisions),
        "level": "dangerous" if any(item["level"] == "dangerous" for item in items) else "review" if items else "safe",
        "requires_approval": sum(1 for decision in decisions if decision.requires_approval),
        "blocked": sum(1 for decision in decisions if decision.validation_error()),
        "by_action_class": {
            "external": sum(1 for decision in decisions if decision.action_class == "external"),
            "mutating": sum(1 for decision in decisions if decision.action_class == "mutating"),
            "dangerous": sum(1 for decision in decisions if decision.action_class == "dangerous"),
        },
        "items": items,
    }


def validate_execution_policy_guardrails(
    *,
    nodes: list[dict[str, Any]],
    id_to_node: dict[str, dict[str, Any]],
    incoming_edges: dict[str, list[dict[str, Any]]],
) -> list[str]:
    errors: list[str] = []
    for decision in build_execution_policy_decisions(
        nodes=nodes,
        id_to_node=id_to_node,
        incoming_edges=incoming_edges,
    ):
        error = decision.validation_error()
        if error:
            errors.append(error)
    return errors
