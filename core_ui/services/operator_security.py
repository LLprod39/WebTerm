"""Security helpers for Operator actions (typed confirm for destructive work)."""

from __future__ import annotations

from typing import Any

from app.tools.safety import evaluate_command_safety
from core_ui.models import AssistantAction


def _command_from_payload(payload: dict[str, Any] | None) -> str:
    data = payload or {}
    return str(data.get("command") or data.get("cmd") or "").strip()


def _server_token_from_payload(payload: dict[str, Any] | None, blast: dict[str, Any] | None) -> str:
    data = payload or {}
    blast = blast or {}
    names = blast.get("server_names") if isinstance(blast.get("server_names"), list) else []
    if names:
        return str(names[0] or "").strip()
    for key in ("server_name", "name"):
        if data.get(key):
            return str(data[key]).strip()
    ids = blast.get("server_ids") if isinstance(blast.get("server_ids"), list) else []
    if len(ids) > 1:
        return "FANOUT"
    if data.get("server_id"):
        return str(data.get("server_id")).strip()
    return ""


# Never require typing for these — simple click confirm is enough.
_CLICK_ONLY_ACTION_TYPES = frozenset(
    {
        "agent.create",
        "agent.run",
        "agent.stop",
        "agents.list",
        "operator.propose_plan",
    }
)


def should_require_typed_confirm(
    *,
    action_type: str,
    risk: str,
    input_payload: dict[str, Any] | None = None,
    blast_radius: dict[str, Any] | None = None,
) -> bool:
    """Typed confirm only for truly destructive shell/fan-out work.

    agent.create / agent.run / normal read-ish mutates: one-click confirm.
    """
    at = str(action_type or "").strip()
    if at in _CLICK_ONLY_ACTION_TYPES or at.startswith("agent."):
        return False

    blast = blast_radius or {}
    # Multi-host fan-out only
    if at in {"operator.run_fanout"} or "fanout" in at:
        ids = blast.get("server_ids") if isinstance(blast.get("server_ids"), list) else []
        if len(ids) > 1:
            return True

    cmd = _command_from_payload(input_payload)
    if cmd:
        verdict = evaluate_command_safety(cmd)
        if verdict.is_dangerous:
            return True
    return risk == AssistantAction.RISK_DANGEROUS


def build_typed_confirm_meta(
    *,
    action_type: str,
    risk: str,
    input_payload: dict[str, Any] | None = None,
    blast_radius: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return blast_radius enrichment for typed confirm UI."""
    blast = dict(blast_radius or {})
    if not should_require_typed_confirm(
        action_type=action_type,
        risk=risk,
        input_payload=input_payload,
        blast_radius=blast,
    ):
        blast.pop("typed_confirm_required", None)
        blast.pop("typed_confirm_token", None)
        blast.pop("typed_confirm_hint", None)
        return blast

    token = _server_token_from_payload(input_payload, blast)
    if not token:
        token = "CONFIRM"
    blast["typed_confirm_required"] = True
    blast["typed_confirm_token"] = token
    if token == "FANOUT":
        count = len(blast.get("server_ids") or []) or "several"
        blast["typed_confirm_hint"] = f"Type FANOUT to confirm multi-host action ({count} hosts)"
    else:
        blast["typed_confirm_hint"] = f"Type the server name exactly: {token}"
    cmd = _command_from_payload(input_payload)
    if cmd:
        risk_info = evaluate_command_safety(cmd)
        if risk_info.is_dangerous:
            blast["command_risk"] = {
                "level": "dangerous",
                "categories": list(risk_info.categories),
                "patterns": list(risk_info.matched_patterns),
            }
    return blast


def action_requires_typed_confirm(action: AssistantAction) -> bool:
    """A persisted typed-confirm flag is authoritative — the gate fails closed.

    Recomputation may only ADD strictness (policy got stricter since the
    action was created); it must never silently remove a stored gate, or a
    destructive action slips through with an empty confirmation.
    """
    blast = action.blast_radius if isinstance(action.blast_radius, dict) else {}
    if blast.get("typed_confirm_required"):
        return True
    return should_require_typed_confirm(
        action_type=action.action_type,
        risk=action.risk,
        input_payload=action.input_payload if isinstance(action.input_payload, dict) else {},
        blast_radius=blast,
    )


def validate_typed_confirm(action: AssistantAction, typed_value: str | None) -> str | None:
    """Return error message if typed confirm fails, else None."""
    if not action_requires_typed_confirm(action):
        return None
    blast = action.blast_radius if isinstance(action.blast_radius, dict) else {}
    expected = str(blast.get("typed_confirm_token") or "").strip()
    if not expected:
        expected = (
            _server_token_from_payload(
                action.input_payload if isinstance(action.input_payload, dict) else {},
                blast,
            )
            or "CONFIRM"
        )
    provided = str(typed_value or "").strip()
    if not provided:
        return f'Typed confirmation required. Type "{expected}" to proceed.'
    if provided != expected:
        # Case-insensitive for server names, strict for FANOUT
        if expected == "FANOUT":
            if provided.upper() != "FANOUT":
                return f'Typed confirmation mismatch. Type "{expected}" exactly.'
            return None
        if provided.casefold() != expected.casefold():
            return f'Typed confirmation mismatch. Expected "{expected}".'
    return None
