from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from studio.policy.execution_policy_audit import decision_audit_metadata

PolicyRiskLevel = Literal["review", "dangerous"]
PolicyActionClass = Literal["external", "mutating", "dangerous"]


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
            "audit_metadata": decision_audit_metadata(self),
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
    return {_node_id(node): node for node in nodes if isinstance(node, dict) and _node_id(node)}


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
        if (
            str(source_node.get("type") or "") == "logic/human_approval"
            and _normalized_handle(edge.get("sourceHandle")) == "approved"
        ):
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
