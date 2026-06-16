from __future__ import annotations

from typing import Any

from app.egress_redaction import payload_preview, redact_egress_payload
from app.tools.safety import evaluate_command_safety


def safe_payload_preview(payload: Any, *, limit: int = 800) -> str:
    redacted, _report, _hashes = redact_egress_payload(payload or {})
    return payload_preview(redacted, limit=limit)


def infer_operation_kind(tool_name: str, args: dict[str, Any] | None = None) -> str:
    name = str(tool_name or "").strip()
    args = args or {}
    if name in {"ssh_execute", "server_execute"}:
        return "ssh_command"
    if name.startswith("mcp_"):
        return "mcp_call"
    if "command" in args or "cmd" in args:
        return "command"
    if "path" in args and any(key in args for key in ("content", "mode", "owner", "group")):
        return "file_mutation"
    if "path" in args:
        return "file_access"
    return name or "tool_call"


def infer_target(args: dict[str, Any] | None = None) -> str:
    args = args or {}
    for key in (
        "server_name_or_id",
        "server",
        "target",
        "conn_id",
        "server_id",
        "mcp_server_id",
        "url",
        "path",
    ):
        value = args.get(key)
        if value not in (None, ""):
            return str(value)
    return ""


def build_execution_policy_audit_metadata(
    *,
    tool_name: str,
    args: dict[str, Any] | None,
    mode: str,
    allowed: bool,
    sandbox_profile: str = "",
    reason: str = "",
    requires_approval: bool = False,
    operation_kind: str = "",
    target: str = "",
    risk_categories: tuple[str, ...] = (),
    matched_patterns: tuple[str, ...] = (),
    actor: str = "",
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    safe_args = args or {}
    command = str(safe_args.get("command") or safe_args.get("cmd") or "")
    command_risk = evaluate_command_safety(command)
    categories = tuple(risk_categories or command_risk.categories)
    patterns = tuple(matched_patterns or command_risk.matched_patterns)
    op_kind = operation_kind or infer_operation_kind(tool_name, safe_args)
    target_value = target or infer_target(safe_args)
    redacted_payload, redaction_report, secret_hashes = redact_egress_payload(
        {
            "tool": tool_name,
            "operation_kind": op_kind,
            "target": target_value,
            "args": safe_args,
        }
    )
    metadata: dict[str, Any] = {
        "version": 1,
        "actor": str(actor or ""),
        "tool": str(tool_name or ""),
        "operation_kind": op_kind,
        "target": target_value,
        "policy_mode": str(mode or ""),
        "allowed": bool(allowed),
        "requires_approval": bool(requires_approval),
        "sandbox_profile": str(sandbox_profile or ""),
        "risk_categories": list(categories),
        "matched_patterns": list(patterns),
        "reason": str(reason or ""),
        "redacted_preview": payload_preview(redacted_payload, limit=800),
        "redaction_report": redaction_report,
        "redacted_secret_count": len(secret_hashes),
    }
    if extra:
        metadata.update(extra)
    return metadata
