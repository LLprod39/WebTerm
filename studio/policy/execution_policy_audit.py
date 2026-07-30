from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.execution_policy import build_execution_policy_audit_metadata

if TYPE_CHECKING:
    from studio.policy.execution_policy import ExecutionPolicyDecision


def _operation_kind(decision: ExecutionPolicyDecision) -> str:
    if decision.node_type == "agent/ssh_cmd":
        return "ssh_command"
    if decision.node_type == "agent/mcp_call":
        return "mcp_call"
    if decision.action_class == "external":
        return f"external_{decision.stage}"
    if decision.node_type.startswith("ops/"):
        return f"ops_{decision.stage}"
    return f"studio_{decision.action_class}"


def decision_audit_metadata(decision: ExecutionPolicyDecision) -> dict[str, Any]:
    return build_execution_policy_audit_metadata(
        tool_name=decision.node_type or decision.stage,
        args={
            "node_id": decision.node_id,
            "node_label": decision.node_label,
            "node_type": decision.node_type,
            "stage": decision.stage,
            "action_class": decision.action_class,
            "command": decision.command,
        },
        mode="studio_graph_validation",
        allowed=decision.allowed,
        reason="; ".join(decision.reasons),
        requires_approval=decision.requires_approval,
        operation_kind=_operation_kind(decision),
        target=decision.node_id,
        risk_categories=decision.categories,
        matched_patterns=decision.matched_patterns,
        extra={
            "policy_source": "studio_graph_validation",
            "level": decision.level,
            "has_approved_approval_path": decision.has_approved_approval_path,
        },
    )
