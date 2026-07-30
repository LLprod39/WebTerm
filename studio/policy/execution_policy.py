from __future__ import annotations

from typing import Any

from studio.policy.execution_policy_classify import (
    MCP_MUTATING_TOOL_RE,
    SSH_MUTATING_COMMAND_RE,
    _classify_dynamic_agent,
    _classify_external_output,
    _classify_mcp_call,
    _classify_ops_action,
    _classify_ssh_cmd,
)
from studio.policy.execution_policy_types import (
    ExecutionPolicyDecision,
    PolicyActionClass,
    PolicyRiskLevel,
    _approval_state,
    _decision,
    _id_map,
    _incoming_map,
    _is_nonblank,
    _node_data,
    _node_id,
    _node_label,
    _normalized_handle,
)

__all__ = [
    "ExecutionPolicyDecision",
    "MCP_MUTATING_TOOL_RE",
    "PolicyActionClass",
    "PolicyRiskLevel",
    "SSH_MUTATING_COMMAND_RE",
    "_approval_state",
    "_classify_dynamic_agent",
    "_classify_external_output",
    "_classify_mcp_call",
    "_classify_ops_action",
    "_classify_ssh_cmd",
    "_decision",
    "_id_map",
    "_incoming_map",
    "_is_nonblank",
    "_node_data",
    "_node_id",
    "_node_label",
    "_normalized_handle",
    "build_execution_policy_decisions",
    "summarize_execution_policy_decisions",
    "validate_execution_policy_guardrails",
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
        elif node_type in {"agent/react", "agent/multi"}:
            decisions.extend(_classify_dynamic_agent(node, has_approved_approval_path=has_approval))
        elif node_type == "agent/ssh_cmd":
            decisions.extend(_classify_ssh_cmd(node, has_approved_approval_path=has_approval))
        elif node_type in {
            "ops/service_action",
            "ops/docker_action",
            "ops/process_action",
            "ops/file_action",
            "ops/package_action",
            "ops/disk_cleanup",
            "ops/alert_update",
        }:
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
